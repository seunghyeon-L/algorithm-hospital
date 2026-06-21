# -*- coding: utf-8 -*-
"""Part B — native-speed (Numba/LLVM-JIT) decoder + SA, engine-faithful to the
Python greedy_resource_schedule.

We re-implement the SAME event-based serial-SGS decoder on flat int64 arrays and
JIT-compile it to machine code (no C++ compiler needed; numba uses LLVM). The
goal is to answer: "if the metaheuristic's hot loop ran at native speed instead
of pure Python, where does the SA-vs-CP-SAT crossover move?"

Correctness gate: `verify()` checks that the numba decoder's Σwait equals the
Python decoder's Σwait on topological order AND random orders, across N. Only a
PASS makes the experiment meaningful.
"""
from __future__ import annotations
import sys, time, csv, os
import numpy as np
from numba import njit

from backend.app.data import generate_jnuh_instance
from backend.app.baseline import schedule_baseline, greedy_resource_schedule
from backend.app.rcpsp import schedule_rcpsp
from backend.app import graph as _graph


# ---------------------------------------------------------------------------
# Flatten an Instance into numba-friendly int64 arrays
# ---------------------------------------------------------------------------
def extract_arrays(inst):
    tids = list(inst.tasks.keys())
    idx = {t: i for i, t in enumerate(tids)}
    T = len(tids)
    res_names = list(inst.resource_capacities.keys())
    R = len(res_names)
    ridx = {r: i for i, r in enumerate(res_names)}
    caps = np.array([inst.resource_capacities[r] for r in res_names], dtype=np.int64)
    room_idx = ridx.get("room", -1)
    dur = np.zeros(T, np.int64)
    pred = np.full(T, -1, np.int64)
    demand = np.zeros((T, R), np.int64)
    for tid in tids:
        i = idx[tid]
        task = inst.tasks[tid]
        dur[i] = task.duration
        ps = list(task.predecessors)
        if len(ps) > 1:
            raise ValueError("numba_engine assumes single-predecessor chains (JNUH).")
        if ps:
            pred[i] = idx[ps[0]]
        for r, d in (task.resources or {}).items():
            if r in ridx:
                demand[i, ridx[r]] = d
    turnover = int(getattr(inst, "turnover", 0) or 0)
    return dur, pred, demand, caps, room_idx, turnover, tids, idx


# ---------------------------------------------------------------------------
# Numba decoder — faithful port of _ResourceTracker / greedy_resource_schedule
# Returns Σwait = Σ (start - ready).  Room labels are irrelevant to Σwait so we
# skip pick_room entirely.
# ---------------------------------------------------------------------------
@njit(cache=True)
def _ub(et, n, x):
    # first index i in [0,n) with et[i] > x  (upper bound)
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        if et[mid] <= x:
            lo = mid + 1
        else:
            hi = mid
    return lo


@njit(cache=True)
def _lb(et, n, x):
    # first index i in [0,n) with et[i] >= x  (lower bound)
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        if et[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return lo


@njit(cache=True)
def _insert(et, ed, ec, cnt, time_v, delta):
    # bisect_left by tuple (time, delta): first i with (et[i],ed[i]) >= (time,delta)
    lo, hi = 0, cnt
    while lo < hi:
        mid = (lo + hi) // 2
        if et[mid] < time_v or (et[mid] == time_v and ed[mid] < delta):
            lo = mid + 1
        else:
            hi = mid
    pos = lo
    # shift [pos, cnt) right by 1
    for i in range(cnt, pos, -1):
        et[i] = et[i - 1]
        ed[i] = ed[i - 1]
    et[pos] = time_v
    ed[pos] = delta
    cnt2 = cnt + 1
    # recompute cumulative suffix from pos
    running = ec[pos - 1] if pos > 0 else 0
    for i in range(pos, cnt2):
        running += ed[i]
        ec[i] = running
    return cnt2


@njit(cache=True)
def _earliest_free(et, ed, ec, cnt, ready, dur, dem, cap, extra):
    threshold = cap - dem
    t = ready
    while True:
        occ_end = t + dur + extra
        lo = _ub(et, cnt, t)
        usage = ec[lo - 1] if lo > 0 else 0
        if usage > threshold:
            found = False
            for i in range(lo, cnt):
                if ed[i] < 0:
                    t = et[i]
                    found = True
                    break
            if not found:
                return t
            continue
        hi = _lb(et, cnt, occ_end)
        running = usage
        ok = True
        next_t = -1
        for i in range(lo, hi):
            running += ed[i]
            if running > threshold:
                nt = -1
                for j in range(i + 1, cnt):
                    if ed[j] < 0:
                        nt = et[j]
                        break
                next_t = nt if nt >= 0 else occ_end
                ok = False
                break
        if ok:
            return t
        t = next_t


@njit(cache=True)
def decode_sigma(order, dur, pred, demand, caps, room_idx, turnover):
    T = dur.shape[0]
    R = caps.shape[0]
    cap = 2 * T + 4
    et = np.zeros((R, cap), np.int64)
    ed = np.zeros((R, cap), np.int64)
    ec = np.zeros((R, cap), np.int64)
    cnt = np.zeros(R, np.int64)

    placed = np.zeros(T, np.uint8)
    finished = np.zeros(T, np.int64)
    nplaced = 0
    sigma = 0

    progressed = True
    while nplaced < T and progressed:
        progressed = False
        for oi in range(T):
            tk = order[oi]
            if placed[tk]:
                continue
            p = pred[tk]
            if p >= 0 and placed[p] == 0:
                continue
            ready = finished[p] if p >= 0 else 0
            d = dur[tk]
            # earliest_feasible_start: fixpoint over resources
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
            # add intervals to each demanded resource
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
            sigma += start - ready
            progressed = True
    return sigma


# ---------------------------------------------------------------------------
# Numba SA — chunked so the wall-clock check happens in Python between chunks
# ---------------------------------------------------------------------------
@njit(cache=True)
def _sa_chunk(cur, cur_cost, best, best_cost, temp, cooling, t_end,
              dur, pred, demand, caps, room_idx, turnover, n_iters):
    T = cur.shape[0]
    for _ in range(n_iters):
        i = np.random.randint(0, T)
        j = np.random.randint(0, T)
        while j == i:
            j = np.random.randint(0, T)
        tmp = cur[i]; cur[i] = cur[j]; cur[j] = tmp
        cand_cost = decode_sigma(cur, dur, pred, demand, caps, room_idx, turnover)
        delta = cand_cost - cur_cost
        if delta <= 0 or np.random.random() < np.exp(-delta / (temp if temp > 1e-9 else 1e-9)):
            cur_cost = cand_cost
            if cur_cost < best_cost:
                best_cost = cur_cost
                for k in range(T):
                    best[k] = cur[k]
        else:
            tmp2 = cur[i]; cur[i] = cur[j]; cur[j] = tmp2  # revert swap
        temp = temp * cooling
        if temp < t_end:
            temp = t_end
    return cur_cost, best_cost, temp


def sa_native(inst, seed=42, budget=15.0, chunk=2000):
    dur, pred, demand, caps, room_idx, turnover, tids, idx = extract_arrays(inst)
    topo = _graph.topological_order(inst)
    order0 = np.array([idx[t] for t in topo], np.int64)
    np.random.seed(seed)
    cur = order0.copy()
    best = order0.copy()
    cur_cost = int(decode_sigma(cur, dur, pred, demand, caps, room_idx, turnover))
    best_cost = cur_cost
    temp = max(10.0, cur_cost * 0.15)
    t0 = time.perf_counter()
    iters = 0
    while time.perf_counter() - t0 < budget:
        cur_cost, best_cost, temp = _sa_chunk(
            cur, cur_cost, best, best_cost, temp, 0.9975, 0.5,
            dur, pred, demand, caps, room_idx, turnover, chunk)
        iters += chunk
    return int(best_cost), iters, time.perf_counter() - t0


# ---------------------------------------------------------------------------
# Native GA — Python orchestration (cheap) + numba decode for fitness (hot)
# ---------------------------------------------------------------------------
def _ox(p1, p2, rng):
    """Ordered crossover (OX) for permutations -> child permutation."""
    n = len(p1)
    a = rng.randrange(n); b = rng.randrange(n)
    if a > b:
        a, b = b, a
    child = np.full(n, -1, np.int64)
    child[a:b + 1] = p1[a:b + 1]
    used = set(int(x) for x in p1[a:b + 1])
    fill = [int(x) for x in p2 if int(x) not in used]
    k = 0
    for i in range(n):
        if child[i] == -1:
            child[i] = fill[k]; k += 1
    return child


def _tournament(pop, fit, tour, rng):
    cand = rng.sample(range(len(pop)), tour)
    bi = cand[0]
    for c in cand[1:]:
        if fit[c] < fit[bi]:
            bi = c
    return pop[bi]


def ga_native(inst, seed=42, budget=15.0, pop_size=30, tour=3, cx=0.8, mut=0.2,
              seed_baseline=False):
    """GA whose fitness eval (the bottleneck) uses the numba decoder.

    seed_baseline=True injects ONE individual = the greedy/topological baseline
    order into the initial population (the rest stay random). This is the
    standard 'seeded/memetic GA' init; with elitism it guarantees the GA never
    ends worse than the baseline (the opponent's plain GA seeds similarly).
    """
    import random as _r
    dur, pred, demand, caps, room_idx, turnover, tids, idx = extract_arrays(inst)
    rng = _r.Random(seed)
    np.random.seed(seed)
    T = len(tids)

    def ev(order):
        return int(decode_sigma(order, dur, pred, demand, caps, room_idx, turnover))

    pop = [np.random.permutation(T).astype(np.int64) for _ in range(pop_size)]
    if seed_baseline:
        topo = _graph.topological_order(inst)
        pop[0] = np.array([idx[t] for t in topo], np.int64)  # 1 baseline seed, rest random
    fit = [ev(ind) for ind in pop]
    decodes = pop_size
    bi = int(np.argmin(np.array(fit)))
    best = pop[bi].copy(); best_f = fit[bi]
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < budget:
        newpop = [best.copy()]; newfit = [best_f]  # elitism
        while len(newpop) < pop_size:
            p1 = _tournament(pop, fit, tour, rng)
            p2 = _tournament(pop, fit, tour, rng)
            child = _ox(p1, p2, rng) if rng.random() < cx else p1.copy()
            if rng.random() < mut:
                i = rng.randrange(T); j = rng.randrange(T)
                tmp = child[i]; child[i] = child[j]; child[j] = tmp
            f = ev(child); decodes += 1
            newpop.append(child); newfit.append(f)
            if f < best_f:
                best_f = f; best = child.copy()
            if time.perf_counter() - t0 >= budget:
                break
        pop, fit = newpop, newfit
    return int(best_f), decodes, time.perf_counter() - t0


# ---------------------------------------------------------------------------
# Correctness gate
# ---------------------------------------------------------------------------
def verify():
    print("# VERIFY numba decoder == python decoder (Σwait)", flush=True)
    ok = True
    for N in (20, 50, 100):
        inst = generate_jnuh_instance(n_patients=N, seed=42)
        dur, pred, demand, caps, room_idx, turnover, tids, idx = extract_arrays(inst)
        # topo order
        topo = _graph.topological_order(inst)
        order = np.array([idx[t] for t in topo], np.int64)
        nb = int(decode_sigma(order, dur, pred, demand, caps, room_idx, turnover))
        py = schedule_baseline(inst).total_wait(inst)
        # a few random precedence-respecting-ish orders via python decoder for cross-check
        import random as _r
        rng = _r.Random(7)
        diffs = []
        for _ in range(3):
            perm = list(range(len(tids)))
            rng.shuffle(perm)
            nb_r = int(decode_sigma(np.array(perm, np.int64), dur, pred, demand, caps, room_idx, turnover))
            py_order = [tids[k] for k in perm]
            py_r = greedy_resource_schedule(inst, py_order).total_wait(inst)
            diffs.append(nb_r - py_r)
        match = (nb == py) and all(d == 0 for d in diffs)
        ok = ok and match
        print(f"N={N:>4} tasks={len(tids):>4}  topo: numba={nb} python={py}  random diffs={diffs}  -> {'OK' if match else 'MISMATCH'}", flush=True)
    print(f"# VERIFY {'PASS' if ok else 'FAIL'}", flush=True)
    return ok


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "scale":
        BUDGET = 15.0
        SEED = 42
        N_LIST = [100, 150, 200, 300, 400, 500, 700, 1000]
        OUT = os.path.join(os.path.dirname(__file__), "_crossover_numba.csv")
        if not verify():
            print("ABORT: decoder mismatch", flush=True)
            sys.exit(1)
        print(f"\n# Part B — NUMBA native engine | budget={BUDGET}s seed={SEED}", flush=True)
        print(f"{'N':>5}{'tasks':>7}{'base':>11}{'CP':>11}{'CP%':>7}{'SAnb':>11}{'SA%':>7}{'SAit':>9}  winner", flush=True)
        rows = []
        for N in N_LIST:
            inst = generate_jnuh_instance(n_patients=N, seed=SEED)
            T = len(inst.tasks)
            bw = schedule_baseline(inst).total_wait(inst)
            cw = schedule_rcpsp(inst, time_limit_sec=BUDGET, random_seed=SEED).total_wait(inst)
            sw, sit, swall = sa_native(inst, seed=SEED, budget=BUDGET)
            cp_p = (cw - bw) / bw * 100
            sa_p = (sw - bw) / bw * 100
            winner = "SA" if sw < cw else ("CP-SAT" if cw < sw else "tie")
            print(f"{N:>5}{T:>7}{bw:>11}{cw:>11}{cp_p:>6.1f}%{sw:>11}{sa_p:>6.1f}%{sit:>9}  {winner}", flush=True)
            rows.append({"N": N, "tasks": T, "baseline": bw, "cpsat": cw, "cp_pct": round(cp_p, 2),
                         "sa_numba": sw, "sa_pct": round(sa_p, 2), "sa_iters": sit, "winner": winner})
            with open(OUT, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
        cross = next((r["N"] for r in rows if r["sa_numba"] < r["cpsat"]), None)
        print(f"\n# numba crossover (first N where SA beats CP-SAT): {cross}", flush=True)
        print(f"# CSV -> {OUT}", flush=True)
    elif len(sys.argv) > 1 and sys.argv[1] == "ga":
        BUDGET = 15.0
        SEED = 42
        N_LIST = [100, 150, 200, 300, 400, 500, 700, 1000]
        OUT = os.path.join(os.path.dirname(__file__), "_crossover_numba_ga.csv")
        if not verify():
            print("ABORT: decoder mismatch", flush=True)
            sys.exit(1)
        print(f"\n# Part B-GA — NUMBA native GA | budget={BUDGET}s seed={SEED}", flush=True)
        print(f"{'N':>5}{'tasks':>7}{'base':>11}{'GAnb':>11}{'GA%':>7}{'decodes':>9}", flush=True)
        rows = []
        for N in N_LIST:
            inst = generate_jnuh_instance(n_patients=N, seed=SEED)
            T = len(inst.tasks)
            bw = schedule_baseline(inst).total_wait(inst)
            gw, dec, wall = ga_native(inst, seed=SEED, budget=BUDGET)
            ga_p = (gw - bw) / bw * 100
            print(f"{N:>5}{T:>7}{bw:>11}{gw:>11}{ga_p:>6.1f}%{dec:>9}", flush=True)
            rows.append({"N": N, "tasks": T, "baseline": bw, "ga_numba": gw, "ga_pct": round(ga_p, 2), "decodes": dec})
            with open(OUT, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
        print(f"# CSV -> {OUT}", flush=True)
    else:
        verify()
