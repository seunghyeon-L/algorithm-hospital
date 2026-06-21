# -*- coding: utf-8 -*-
"""jnuh5_algos.py — schedulers for the 5-stage JNUH study.

All metaheuristics optimise a PLUGGABLE objective via the shared Serial-SGS
decoder (greedy_resource_schedule).  Set `weighted=True` for the KTAS-weighted
objective, `weighted=False` for the unweighted Σwait (PINNED).

Algorithms:
  baseline   — topological-greedy (intentional naive reference)
  sa         — simulated annealing (geometric cooling, Metropolis)
  ga         — genetic algorithm (OX crossover, swap/insert mutation, tournament)
  ga(seeded) — GA whose initial population is seeded with heuristic orders
  hga        — hybrid GA = GA then hill-climbing local search (opponent-style)
  cpsat      — OR-Tools CP-SAT exact (interval model, release, warm-start)
  scil       — SA -> CP-SAT warm-start hybrid

Each returns a model.Schedule with `.algo` and `.wall_clock_sec` set.
"""
from __future__ import annotations

import math
import random
import time
from typing import Callable, Dict, List, Optional, Tuple

from backend.app.model import Instance, Schedule, TaskAssignment
from backend.app import graph as _graph
from backend.app.jnuh5 import Jnuh5Instance, decode, objective_value, task_order

# ---------------------------------------------------------------------------
# Heuristic priority orders (used as seeds and as the 6-rule baseline family)
# ---------------------------------------------------------------------------

def heuristic_orders(ji: Jnuh5Instance) -> Dict[str, List[str]]:
    """The opponent's 6 dispatching rules, as task_id priority lists."""
    inst = ji.instance
    pts = ji.patients
    tids = list(inst.tasks.keys())
    from backend.app.jnuh5 import STAGE_ORDER

    def pw(tid: str) -> int:
        return pts[inst.tasks[tid].patient_id].weight

    def arr(tid: str) -> int:
        return pts[inst.tasks[tid].patient_id].arrival

    topo = task_order(inst)
    cp_len, _ = _graph.critical_path(inst)
    # bottom-level (longest remaining path) for critical-path rule
    bottom = _bottom_levels(inst)
    return {
        "Topological": topo,
        "FCFS": sorted(tids, key=lambda t: (arr(t), STAGE_ORDER[inst.tasks[t].label.split("·")[-1]], t)),
        "SPT": sorted(tids, key=lambda t: (inst.tasks[t].duration, t)),
        "LPT": sorted(tids, key=lambda t: (-inst.tasks[t].duration, t)),
        "Urgency": sorted(tids, key=lambda t: (-pw(t), arr(t), t)),
        "CriticalPath": sorted(tids, key=lambda t: (-bottom.get(t, 0), t)),
    }


def _bottom_levels(inst: Instance) -> Dict[str, int]:
    """Longest remaining duration path from each task to a sink (for CP rule)."""
    topo = task_order(inst)
    succ: Dict[str, List[str]] = {t: [] for t in inst.tasks}
    for u, v in inst.edges():
        succ[u].append(v)
    bottom: Dict[str, int] = {}
    for t in reversed(topo):
        d = inst.tasks[t].duration
        bottom[t] = d + max((bottom[s] for s in succ[t]), default=0)
    return bottom


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------

def baseline(ji: Jnuh5Instance) -> Schedule:
    t0 = time.perf_counter()
    sched = decode(ji.instance, task_order(ji.instance), algo="baseline")
    sched.wall_clock_sec = time.perf_counter() - t0
    sched.validate(ji.instance)
    return sched


# ---------------------------------------------------------------------------
# Permutation operators
# ---------------------------------------------------------------------------

def _ox(a: List[str], b: List[str], rng: random.Random) -> List[str]:
    """Ordered crossover (OX): a-prefix then b's remaining in order."""
    n = len(a)
    if n < 2:
        return a[:]
    cut = rng.randrange(1, n)
    prefix = a[:cut]
    used = set(prefix)
    return prefix + [t for t in b if t not in used]


def _swap(order: List[str], rng: random.Random) -> List[str]:
    o = order[:]
    if len(o) < 2:
        return o
    i, j = rng.sample(range(len(o)), 2)
    o[i], o[j] = o[j], o[i]
    return o


def _insert(order: List[str], rng: random.Random) -> List[str]:
    o = order[:]
    if len(o) < 2:
        return o
    i = rng.randrange(len(o))
    item = o.pop(i)
    j = rng.randrange(len(o) + 1)
    o.insert(j, item)
    return o


def _neighbor(order: List[str], rng: random.Random) -> List[str]:
    return _insert(order, rng) if rng.random() < 0.8 else _swap(order, rng)


# ---------------------------------------------------------------------------
# Simulated annealing
# ---------------------------------------------------------------------------

def sa(ji: Jnuh5Instance, *, weighted: bool, budget: float = 15.0,
       seed: int = 1000) -> Schedule:
    t0 = time.perf_counter()
    rng = random.Random(seed)
    inst = ji.instance
    # start from the best available heuristic order (guarantees SA <= baseline)
    cur, cur_obj, cur_sched = _best_heuristic(ji, weighted)
    best, best_obj, best_sched = cur, cur_obj, cur_sched

    T0 = max(1.0, 0.15 * max(1.0, cur_obj))
    Tend = max(0.01, 0.001 * T0)
    it = 0
    # estimate iterations by time; use a smooth cooling vs elapsed fraction
    while time.perf_counter() - t0 < budget:
        frac = min(1.0, (time.perf_counter() - t0) / budget)
        temp = T0 * ((Tend / T0) ** frac)
        cand = _neighbor(cur, rng)
        obj, sched = _eval(ji, cand, weighted)
        if obj <= cur_obj or rng.random() < math.exp(-(obj - cur_obj) / max(temp, 1e-9)):
            cur, cur_obj, cur_sched = cand, obj, sched
        if obj < best_obj:
            best, best_obj, best_sched = cand, obj, sched
        it += 1
    best_sched.algo = "SA"
    best_sched.wall_clock_sec = time.perf_counter() - t0
    best_sched.validate(inst)
    return best_sched


# ---------------------------------------------------------------------------
# Genetic algorithm (+ optional seeding)
# ---------------------------------------------------------------------------

def ga(ji: Jnuh5Instance, *, weighted: bool, budget: float = 15.0,
       pop_size: int = 30, tour: int = 3, cx: float = 0.85,
       seed: int = 2000, seeded: bool = False, algo: str = "GA") -> Schedule:
    t0 = time.perf_counter()
    rng = random.Random(seed)
    inst = ji.instance
    tids = list(inst.tasks.keys())

    # --- initial population ---
    pop: List[List[str]] = []
    if seeded:
        for o in heuristic_orders(ji).values():
            pop.append(o[:])
    else:
        pop.append(task_order(inst))            # one valid seed always
    while len(pop) < pop_size:
        p = tids[:]
        rng.shuffle(p)
        pop.append(p)

    scored = [(_eval(ji, ind, weighted)[0], ind) for ind in pop]
    scored.sort(key=lambda x: x[0])
    elite = max(2, pop_size // 10)

    while time.perf_counter() - t0 < budget:
        new = [scored[i][1][:] for i in range(elite)]
        while len(new) < pop_size:
            a = min(rng.sample(scored, min(tour, len(scored))), key=lambda x: x[0])[1]
            b = min(rng.sample(scored, min(tour, len(scored))), key=lambda x: x[0])[1]
            child = _ox(a, b, rng) if rng.random() < cx else a[:]
            if rng.random() < 0.7:
                child = _insert(child, rng)
            if rng.random() < 0.2:
                child = _swap(child, rng)
            new.append(child)
        scored = [(_eval(ji, ind, weighted)[0], ind) for ind in new]
        scored.sort(key=lambda x: x[0])

    best_obj, best = scored[0]
    _, best_sched = _eval(ji, best, weighted)
    best_sched.algo = algo
    best_sched.wall_clock_sec = time.perf_counter() - t0
    best_sched.validate(inst)
    return best_sched


# ---------------------------------------------------------------------------
# Hybrid GA = GA then hill-climbing local search (opponent-style)
# ---------------------------------------------------------------------------

def hga(ji: Jnuh5Instance, *, weighted: bool, budget: float = 15.0,
        seed: int = 3000) -> Schedule:
    t0 = time.perf_counter()
    # spend ~70% on GA, ~30% on local search
    ga_sched = ga(ji, weighted=weighted, budget=budget * 0.7,
                  seed=seed, seeded=True, algo="HGA")
    rng = random.Random(seed + 997)
    cur = _sched_to_order(ji, ga_sched)
    cur_obj, cur_sched = _eval(ji, cur, weighted)
    best, best_obj, best_sched = cur, cur_obj, cur_sched
    while time.perf_counter() - t0 < budget:
        cands = [_neighbor(cur, rng) for _ in range(4)]
        evals = [(_eval(ji, c, weighted), c) for c in cands]
        (obj, sched), cand = min(evals, key=lambda x: x[0][0])
        if obj <= cur_obj:
            cur, cur_obj, cur_sched = cand, obj, sched
        if obj < best_obj:
            best, best_obj, best_sched = cand, obj, sched
    best_sched.algo = "HGA"
    best_sched.wall_clock_sec = time.perf_counter() - t0
    best_sched.validate(ji.instance)
    return best_sched


# ---------------------------------------------------------------------------
# CP-SAT (exact) — weighted/unweighted, release-aware, warm-startable
# ---------------------------------------------------------------------------

def cpsat(ji: Jnuh5Instance, *, weighted: bool, time_limit: float = 15.0,
          workers: int = 8, warm_order: Optional[List[str]] = None) -> Schedule:
    t0 = time.perf_counter()
    inst = ji.instance
    try:
        from ortools.sat.python import cp_model
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"ortools not available: {exc}")

    tids = list(inst.tasks.keys())
    horizon = (max((inst.tasks[t].release_time for t in tids), default=0)
               + sum(inst.tasks[t].duration for t in tids) + 1)
    m = cp_model.CpModel()
    starts, ends, ivs, readys = {}, {}, {}, {}
    for t in tids:
        d = inst.tasks[t].duration
        rt = inst.tasks[t].release_time
        starts[t] = m.NewIntVar(rt, horizon, f"s_{t}")
        ends[t] = m.NewIntVar(rt, horizon, f"e_{t}")
        ivs[t] = m.NewIntervalVar(starts[t], d, ends[t], f"i_{t}")

    # precedence
    for u, v in inst.edges():
        m.Add(starts[v] >= ends[u])

    # cumulative resources (+ turnover on room via end+turnover intervals)
    turnover = getattr(inst, "turnover", 0) or 0
    for res, cap in inst.resource_capacities.items():
        sel, dem = [], []
        for t in tids:
            d = inst.tasks[t].resources.get(res, 0)
            if d > 0:
                if res == "room" and turnover > 0:
                    e2 = m.NewIntVar(0, horizon + turnover, f"e2_{t}")
                    m.Add(e2 == ends[t] + turnover)
                    sel.append(m.NewIntervalVar(starts[t], inst.tasks[t].duration + turnover, e2, f"ir_{t}"))
                else:
                    sel.append(ivs[t])
                dem.append(d)
        if sel:
            m.AddCumulative(sel, dem, cap)

    # ready_i = max(release, preds' ends); wait_i = start_i - ready_i
    wait_terms = []
    for t in tids:
        task = inst.tasks[t]
        comps = [task.release_time] + [ends[p] for p in task.predecessors]
        ready = m.NewIntVar(0, horizon, f"r_{t}")
        m.AddMaxEquality(ready, comps)
        wait = m.NewIntVar(0, horizon, f"w_{t}")
        m.Add(wait == starts[t] - ready)
        w = ji.patients[task.patient_id].weight if weighted else 1
        wait_terms.append(w * wait)
    m.Minimize(sum(wait_terms))

    # warm start
    if warm_order is not None:
        warm = decode(inst, warm_order)
        for t in tids:
            m.AddHint(starts[t], warm.assignments[t].start)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = int(workers)
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # fall back to baseline if no feasible solution found in time
        sched = baseline(ji)
        sched.algo = "CP-SAT(infeasible-fallback)"
        sched.wall_clock_sec = time.perf_counter() - t0
        return sched

    assignments = {}
    for t in tids:
        s = int(solver.Value(starts[t]))
        assignments[t] = TaskAssignment(task_id=t, start=s, end=s + inst.tasks[t].duration)
    sched = Schedule(instance_id=inst.instance_id, algo="CP-SAT",
                     assignments=assignments,
                     wall_clock_sec=time.perf_counter() - t0)
    sched.validate(inst)
    # anytime guarantee: never return worse than the warm-start solution
    if warm_order is not None:
        warm = decode(inst, warm_order)
        if objective_value(ji, warm, weighted=weighted) < objective_value(ji, sched, weighted=weighted):
            warm.algo = "CP-SAT"
            warm.wall_clock_sec = time.perf_counter() - t0
            return warm
    return sched


# ---------------------------------------------------------------------------
# SCIL = SA -> CP-SAT warm-start hybrid
# ---------------------------------------------------------------------------

def scil(ji: Jnuh5Instance, *, weighted: bool, budget: float = 15.0,
         seed: int = 4000) -> Schedule:
    t0 = time.perf_counter()
    sa_sched = sa(ji, weighted=weighted, budget=budget * 0.5, seed=seed)
    warm = _sched_to_order(ji, sa_sched)
    remaining = max(1.0, budget - (time.perf_counter() - t0))
    cp_sched = cpsat(ji, weighted=weighted, time_limit=remaining, warm_order=warm)
    # return the better of SA and the CP-SAT refinement
    best = min((sa_sched, cp_sched),
               key=lambda s: objective_value(ji, s, weighted=weighted))
    best.algo = "SCIL"
    best.wall_clock_sec = time.perf_counter() - t0
    return best


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _eval(ji: Jnuh5Instance, order: List[str], weighted: bool) -> Tuple[float, Schedule]:
    sched = decode(ji.instance, order)
    return objective_value(ji, sched, weighted=weighted), sched


def _best_heuristic(ji: Jnuh5Instance, weighted: bool) -> Tuple[List[str], float, Schedule]:
    """Best of the 6 heuristic priority orders (objective-minimising seed)."""
    best_order, best_obj, best_sched = None, math.inf, None
    for o in heuristic_orders(ji).values():
        obj, sched = _eval(ji, o, weighted)
        if obj < best_obj:
            best_order, best_obj, best_sched = o, obj, sched
    return best_order, best_obj, best_sched


def _sched_to_order(ji: Jnuh5Instance, sched: Schedule) -> List[str]:
    """Recover a priority order from a schedule (by start time)."""
    return sorted(sched.assignments.keys(),
                  key=lambda t: (sched.assignments[t].start, t))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Emergency scenarios — static (perfect foresight) vs dynamic re-schedule
# ---------------------------------------------------------------------------

def solve_static_emergency(ji: Jnuh5Instance, name: str, *, weighted: bool,
                           budget: float = 15.0, seed: int = 42) -> Schedule:
    """Emergency known a-priori (opponent's approach): solve the full instance once."""
    return run_algorithm(name, ji, weighted=weighted, budget=budget, seed=seed)


def solve_dynamic_emergency(n_patients: int, seed: int, name: str, *,
                            weighted: bool, budget: float = 15.0,
                            emergency_arrival: int = 120) -> Tuple[Schedule, "Jnuh5Instance"]:
    """Dynamic re-scheduling: emergency arrives UNANNOUNCED at t=emergency_arrival.

    1. Plan electives only.
    2. Freeze tasks already started by t_now.
    3. Inject the emergency (high KTAS weight).
    4. Re-optimise the not-yet-started tasks + emergency around the frozen ones.

    Returns (final_schedule, full_instance_with_emergency).
    """
    from backend.app.jnuh5 import generate_jnuh5_instance
    t_start = time.perf_counter()
    t_now = emergency_arrival

    # --- Phase 1: electives only ---
    je = generate_jnuh5_instance(n_patients, seed, include_emergency=False)
    s0 = run_algorithm(name, je, weighted=weighted, budget=budget * 0.5, seed=seed)

    # --- Phase 2: full instance (electives identical by seed + emergency) ---
    j2 = generate_jnuh5_instance(n_patients, seed, include_emergency=True,
                                 emergency_arrival=t_now)
    inst2 = j2.instance
    # original arrival-anchored releases (for meaningful metrics after re-plan)
    orig_release = {t: task.release_time for t, task in inst2.tasks.items()}
    frozen = {t: s0.assignments[t].start
              for t in s0.assignments if s0.assignments[t].start < t_now}
    # patch release times: frozen pinned to committed start; free can't start < t_now
    for t, task in inst2.tasks.items():
        if t in frozen:
            task.release_time = frozen[t]
        elif not j2.patients[task.patient_id].is_emergency:
            task.release_time = max(task.release_time, t_now)

    frozen_order = sorted(frozen, key=lambda t: frozen[t])
    free = [t for t in inst2.tasks if t not in frozen]

    def decode_pinned(free_order: List[str]) -> Schedule:
        # frozen first (release=committed -> placed at committed), then free
        return decode(inst2, frozen_order + free_order)

    def obj(free_order: List[str]) -> Tuple[float, Schedule]:
        sched = decode_pinned(free_order)
        return objective_value(j2, sched, weighted=weighted), sched

    # initial free order = best heuristic order, restricted to free tasks
    free_set = set(free)
    h = heuristic_orders(j2)
    best_h = min(((_eval(j2, list(o), weighted)[0], list(o)) for o in h.values()),
                 key=lambda x: x[0])[1]
    best_free = [t for t in best_h if t in free_set]
    best_obj, best_sched = obj(best_free)

    # hill-climb the free order with remaining budget
    rng = random.Random(seed + 7)
    t0 = time.perf_counter()
    cur, cur_obj = best_free, best_obj
    while time.perf_counter() - t0 < budget * 0.5:
        cand = _neighbor(cur, rng)
        o, sched = obj(cand)
        if o <= cur_obj:
            cur, cur_obj = cand, o
        if o < best_obj:
            best_obj, best_sched, best_free = o, sched, cand

    # restore original arrival-anchored releases so metrics measure true patient
    # waiting (not the re-plan pins).  Final starts still satisfy them (committed
    # >= arrival, free starts >= now >= original release).
    for t, task in inst2.tasks.items():
        task.release_time = orig_release[t]
    best_sched.algo = f"{name}-dynamic"
    best_sched.wall_clock_sec = time.perf_counter() - t_start
    best_sched.validate(inst2)
    return best_sched, j2


def run_algorithm(name: str, ji: Jnuh5Instance, *, weighted: bool,
                  budget: float = 15.0, seed: int = 42) -> Schedule:
    """Dispatch by algorithm name."""
    if name == "baseline":
        return baseline(ji)
    if name == "SA":
        return sa(ji, weighted=weighted, budget=budget, seed=1000 + seed)
    if name == "GA":
        return ga(ji, weighted=weighted, budget=budget, seed=2000 + seed, seeded=False)
    if name == "GA-seeded":
        return ga(ji, weighted=weighted, budget=budget, seed=2500 + seed,
                  seeded=True, algo="GA-seeded")
    if name == "HGA":
        return hga(ji, weighted=weighted, budget=budget, seed=3000 + seed)
    if name == "CP-SAT":
        return cpsat(ji, weighted=weighted, time_limit=budget,
                     warm_order=task_order(ji.instance))
    if name == "SCIL":
        return scil(ji, weighted=weighted, budget=budget, seed=4000 + seed)
    raise ValueError(f"unknown algorithm: {name}")
