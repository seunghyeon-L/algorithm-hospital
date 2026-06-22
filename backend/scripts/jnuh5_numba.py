# -*- coding: utf-8 -*-
"""jnuh5_numba.py — native-speed (Numba/LLVM-JIT) decoder for the 5-stage model.

Generalises the event-based serial-SGS decoder from numba_engine.py to:
  * multi-predecessor DAGs (SURG has 2 preds: PRECHECK ∥ PREP) via a CSR pred list,
  * arbitrary resource types (room/staff/anesthesia/pacu_bed/surgeons) — already
    handled by the demand[T,R] matrix + per-resource event machinery,
  * per-task release_time (patient arrival / emergency).

It computes BOTH the unweighted Σwait and the KTAS-weighted Σ w·wait in one pass.
Correctness gate: verify_5() must show numba == Python decoder on topo + random.
"""
from __future__ import annotations
import time
import numpy as np
from numba import njit

from backend.app.model import Schedule, TaskAssignment
from backend.app.jnuh5 import Jnuh5Instance, objective_value, task_order, decode
# reuse the proven event-machine njit helpers
from backend.scripts.numba_engine import _ub, _lb, _insert, _earliest_free


# ---------------------------------------------------------------------------
# Flatten a Jnuh5Instance into numba-friendly arrays
# ---------------------------------------------------------------------------
def extract_arrays_5(ji: Jnuh5Instance) -> dict:
    inst = ji.instance
    tids = list(inst.tasks.keys())
    idx = {t: i for i, t in enumerate(tids)}
    T = len(tids)
    res_names = list(inst.resource_capacities.keys())
    R = len(res_names)
    ridx = {r: i for i, r in enumerate(res_names)}
    caps = np.array([inst.resource_capacities[r] for r in res_names], np.int64)
    room_idx = ridx.get("room", -1)
    dur = np.zeros(T, np.int64)
    release = np.zeros(T, np.int64)
    demand = np.zeros((T, R), np.int64)
    weights = np.ones(T, np.int64)
    pred_lists = []
    for tid in tids:
        i = idx[tid]
        task = inst.tasks[tid]
        dur[i] = task.duration
        release[i] = task.release_time
        weights[i] = ji.patients[task.patient_id].weight
        for r, d in (task.resources or {}).items():
            if r in ridx:
                demand[i, ridx[r]] = d
        pred_lists.append([idx[p] for p in task.predecessors])
    pred_ptr = np.zeros(T + 1, np.int64)
    for i in range(T):
        pred_ptr[i + 1] = pred_ptr[i] + len(pred_lists[i])
    pred_flat = np.zeros(int(pred_ptr[-1]), np.int64)
    pos = 0
    for i in range(T):
        for p in pred_lists[i]:
            pred_flat[pos] = p
            pos += 1
    return dict(dur=dur, release=release, demand=demand, caps=caps,
                room_idx=room_idx, turnover=int(getattr(inst, "turnover", 0) or 0),
                weights=weights, pred_ptr=pred_ptr, pred_flat=pred_flat,
                tids=tids, idx=idx)


# ---------------------------------------------------------------------------
# Generalised decoder — returns (sigma_unweighted, sigma_weighted, starts)
# ---------------------------------------------------------------------------
@njit(cache=True)
def _decode_core(order, dur, release, demand, caps, room_idx, turnover,
                 weights, pred_ptr, pred_flat, want_starts):
    T = dur.shape[0]
    R = caps.shape[0]
    cap = 2 * T + 4
    et = np.zeros((R, cap), np.int64)
    ed = np.zeros((R, cap), np.int64)
    ec = np.zeros((R, cap), np.int64)
    cnt = np.zeros(R, np.int64)

    placed = np.zeros(T, np.uint8)
    finished = np.zeros(T, np.int64)
    starts = np.full(T, -1, np.int64)
    nplaced = 0
    sig = 0
    sigw = 0
    progressed = True
    while nplaced < T and progressed:
        progressed = False
        for oi in range(T):
            tk = order[oi]
            if placed[tk]:
                continue
            elig = True
            for k in range(pred_ptr[tk], pred_ptr[tk + 1]):
                if placed[pred_flat[k]] == 0:
                    elig = False
                    break
            if not elig:
                continue
            ready = release[tk]
            for k in range(pred_ptr[tk], pred_ptr[tk + 1]):
                pe = finished[pred_flat[k]]
                if pe > ready:
                    ready = pe
            d = dur[tk]
            t = ready
            for _ in range(2 * nplaced + 10):
                new_t = t
                for r in range(R):
                    dem = demand[tk, r]
                    if dem == 0:
                        continue
                    extra = turnover if r == room_idx else 0
                    rt = _earliest_free(et[r], ed[r], ec[r], cnt[r], t, d, dem, caps[r], extra)
                    if rt > new_t:
                        new_t = rt
                if new_t == t:
                    break
                t = new_t
            start = t
            end = start + d
            for r in range(R):
                dem = demand[tk, r]
                if dem == 0:
                    continue
                rel = (end + turnover) if r == room_idx else end
                cnt[r] = _insert(et[r], ed[r], ec[r], cnt[r], rel, -dem)
                cnt[r] = _insert(et[r], ed[r], ec[r], cnt[r], start, dem)
            finished[tk] = end
            placed[tk] = 1
            nplaced += 1
            if want_starts:
                starts[tk] = start
            w = start - ready
            sig += w
            sigw += weights[tk] * w
            progressed = True
    return sig, sigw, starts


def decode_obj(arr: dict, order: np.ndarray, weighted: bool) -> float:
    sig, sigw, _ = _decode_core(
        order, arr["dur"], arr["release"], arr["demand"], arr["caps"],
        arr["room_idx"], arr["turnover"], arr["weights"],
        arr["pred_ptr"], arr["pred_flat"], False)
    return float(sigw if weighted else sig)


def decode_schedule(ji: Jnuh5Instance, arr: dict, order: np.ndarray,
                    algo: str = "native") -> Schedule:
    sig, sigw, starts = _decode_core(
        order, arr["dur"], arr["release"], arr["demand"], arr["caps"],
        arr["room_idx"], arr["turnover"], arr["weights"],
        arr["pred_ptr"], arr["pred_flat"], True)
    tids = arr["tids"]
    inst = ji.instance
    assignments = {}
    for i, tid in enumerate(tids):
        s = int(starts[i])
        assignments[tid] = TaskAssignment(task_id=tid, start=s,
                                          end=s + inst.tasks[tid].duration)
    return Schedule(instance_id=inst.instance_id, algo=algo, assignments=assignments)


# ---------------------------------------------------------------------------
# Correctness gate — numba decoder must equal the Python decoder
# ---------------------------------------------------------------------------
def verify_5(seeds=(1, 2, 3), ns=(20, 50, 100), n_random=3) -> bool:
    import random
    from backend.app.jnuh5 import generate_jnuh5_instance
    ok = True
    print("# VERIFY jnuh5 numba decoder == python decoder")
    for n in ns:
        ji = generate_jnuh5_instance(n, seed=7, include_emergency=True)
        arr = extract_arrays_5(ji)
        idx = arr["idx"]
        # topological order
        topo = np.array([idx[t] for t in task_order(ji.instance)], np.int64)
        py = objective_value(ji, decode(ji.instance, [arr["tids"][i] for i in topo]), weighted=False)
        nb = decode_obj(arr, topo, weighted=False)
        pyw = objective_value(ji, decode(ji.instance, [arr["tids"][i] for i in topo]), weighted=True)
        nbw = decode_obj(arr, topo, weighted=True)
        diffs = []
        rng = random.Random(n)
        for _ in range(n_random):
            perm = list(range(len(topo)))
            rng.shuffle(perm)
            perm_a = np.array(perm, np.int64)
            order_ids = [arr["tids"][i] for i in perm_a]
            p1 = objective_value(ji, decode(ji.instance, order_ids), weighted=False)
            n1 = decode_obj(arr, perm_a, weighted=False)
            diffs.append(int(p1 - n1))
        flag = (py == nb and pyw == nbw and all(d == 0 for d in diffs))
        ok = ok and flag
        print(f"N={n:4} tasks={len(arr['tids']):5} topo py={py:.0f} nb={nb:.0f} "
              f"| wpy={pyw:.0f} wnb={nbw:.0f} | random diffs={diffs} -> {'OK' if flag else 'MISMATCH'}")
    print("# VERIFY", "PASS" if ok else "FAIL")
    return ok


# ---------------------------------------------------------------------------
# Native-speed metaheuristics (hot loop = numba decode_obj)
# ---------------------------------------------------------------------------
import math
import random as _random


def _swap_idx(o, rng):
    o = o[:]
    i, j = rng.sample(range(len(o)), 2)
    o[i], o[j] = o[j], o[i]
    return o


def _insert_idx(o, rng):
    o = o[:]
    i = rng.randrange(len(o))
    x = o.pop(i)
    o.insert(rng.randrange(len(o) + 1), x)
    return o


def _neighbor_idx(o, rng):
    return _insert_idx(o, rng) if rng.random() < 0.8 else _swap_idx(o, rng)


def _ox_idx(a, b, rng):
    n = len(a)
    cut = rng.randrange(1, n)
    pref = a[:cut]
    used = set(pref)
    return pref + [t for t in b if t not in used]


def sa_native(ji: Jnuh5Instance, *, weighted: bool, budget: float = 15.0,
              seed: int = 1000) -> Schedule:
    t0 = time.perf_counter()
    arr = extract_arrays_5(ji)
    idx = arr["idx"]
    rng = _random.Random(seed)
    cur = [idx[t] for t in task_order(ji.instance)]
    cur_obj = decode_obj(arr, np.array(cur, np.int64), weighted)
    best, best_obj = cur[:], cur_obj
    T0 = max(1.0, 0.15 * max(1.0, cur_obj))
    Tend = max(0.01, 0.001 * T0)
    while time.perf_counter() - t0 < budget:
        frac = min(1.0, (time.perf_counter() - t0) / budget)
        temp = T0 * ((Tend / T0) ** frac)
        cand = _neighbor_idx(cur, rng)
        o = decode_obj(arr, np.array(cand, np.int64), weighted)
        if o <= cur_obj or rng.random() < math.exp(-(o - cur_obj) / max(temp, 1e-9)):
            cur, cur_obj = cand, o
        if o < best_obj:
            best, best_obj = cand, o
    sched = decode_schedule(ji, arr, np.array(best, np.int64), algo="SA")
    sched.wall_clock_sec = time.perf_counter() - t0
    sched.validate(ji.instance)
    return sched


def ga_native(ji: Jnuh5Instance, *, weighted: bool, budget: float = 15.0,
              pop_size: int = 30, tour: int = 3, cx: float = 0.85,
              seed: int = 2000, seeded: bool = False, algo: str = "GA") -> Schedule:
    t0 = time.perf_counter()
    arr = extract_arrays_5(ji)
    idx = arr["idx"]
    T = len(arr["tids"])
    rng = _random.Random(seed)

    def ev(o):
        return decode_obj(arr, np.array(o, np.int64), weighted)

    pop = []
    if seeded:
        from backend.app.jnuh5_algos import heuristic_orders
        for o in heuristic_orders(ji).values():
            pop.append([idx[t] for t in o])
    else:
        pop.append([idx[t] for t in task_order(ji.instance)])
    while len(pop) < pop_size:
        p = list(range(T))
        rng.shuffle(p)
        pop.append(p)
    scored = sorted(((ev(ind), ind) for ind in pop), key=lambda x: x[0])
    elite = max(2, pop_size // 10)
    while time.perf_counter() - t0 < budget:
        new = [scored[i][1][:] for i in range(elite)]
        while len(new) < pop_size:
            a = min(rng.sample(scored, min(tour, len(scored))), key=lambda x: x[0])[1]
            b = min(rng.sample(scored, min(tour, len(scored))), key=lambda x: x[0])[1]
            child = _ox_idx(a, b, rng) if rng.random() < cx else a[:]
            if rng.random() < 0.7:
                child = _insert_idx(child, rng)
            if rng.random() < 0.2:
                child = _swap_idx(child, rng)
            new.append(child)
        scored = sorted(((ev(ind), ind) for ind in new), key=lambda x: x[0])
    best = scored[0][1]
    sched = decode_schedule(ji, arr, np.array(best, np.int64), algo=algo)
    sched.wall_clock_sec = time.perf_counter() - t0
    sched.validate(ji.instance)
    return sched


def hga_native(ji: Jnuh5Instance, *, weighted: bool, budget: float = 15.0,
               seed: int = 3000) -> Schedule:
    t0 = time.perf_counter()
    arr = extract_arrays_5(ji)
    g = ga_native(ji, weighted=weighted, budget=budget * 0.7, seed=seed,
                  seeded=False, algo="HGA")
    idx = arr["idx"]
    cur = [idx[t] for t in sorted(g.assignments, key=lambda t: g.assignments[t].start)]
    cur_obj = decode_obj(arr, np.array(cur, np.int64), weighted)
    best, best_obj = cur[:], cur_obj
    rng = _random.Random(seed + 997)
    while time.perf_counter() - t0 < budget:
        cands = [_neighbor_idx(cur, rng) for _ in range(4)]
        evs = [(decode_obj(arr, np.array(c, np.int64), weighted), c) for c in cands]
        o, cand = min(evs, key=lambda x: x[0])
        if o <= cur_obj:
            cur, cur_obj = cand, o
        if o < best_obj:
            best, best_obj = cand, o
    sched = decode_schedule(ji, arr, np.array(best, np.int64), algo="HGA")
    sched.wall_clock_sec = time.perf_counter() - t0
    sched.validate(ji.instance)
    return sched


if __name__ == "__main__":
    verify_5()
