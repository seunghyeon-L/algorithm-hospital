# -*- coding: utf-8 -*-
"""Part A — scaling crossover (pure-Python engine).

When does SA/GA's fixed-budget solution beat CP-SAT's fixed-budget solution?
We scale N (patients) and give every optimizer the SAME 15s wall-clock.
We also record per-instance decode time + estimated iterations so we can SEE
whether a poor result is the algorithm or evaluation starvation.

CP-SAT here is anytime (best-found within 15s, NOT proven optimum) and is
warm-started from the greedy baseline; SA also starts from the greedy/topo
order. So both start from comparable points — the question is who improves
more in 15s as N grows.
"""
from __future__ import annotations
import sys, time, csv, os

from backend.app.data import generate_jnuh_instance
from backend.app.baseline import schedule_baseline, greedy_resource_schedule
from backend.app.rcpsp import schedule_rcpsp
from backend.app.sa import schedule_sa
from backend.app.ga import schedule_ga
from backend.app import graph as _graph

BUDGET = 15.0
SEED = 42
N_LIST = [100, 150, 200, 300, 400, 500, 700, 1000]
GA_POP = 12  # small pop so GA can do >1 generation at large N
OUT_CSV = os.path.join(os.path.dirname(__file__), "_crossover_python.csv")


def one_decode_ms(inst) -> float:
    order = _graph.topological_order(inst)
    t0 = time.perf_counter()
    greedy_resource_schedule(inst, order)
    return (time.perf_counter() - t0) * 1000.0


def run_timed(fn):
    t0 = time.perf_counter()
    sched = fn()
    return sched, time.perf_counter() - t0


print(f"# Part A — Python engine | budget={BUDGET}s seed={SEED} GA_pop={GA_POP}", flush=True)
hdr = f"{'N':>5}{'tasks':>7}{'decMs':>8}{'~it':>7}{'base':>11}{'CP':>11}{'CP%':>7}{'SA':>11}{'SA%':>7}{'GA':>11}{'GA%':>7}  winner   walls(C/S/G)"
print(hdr, flush=True)

rows = []
for N in N_LIST:
    inst = generate_jnuh_instance(n_patients=N, seed=SEED)
    T = len(inst.tasks)
    dms = one_decode_ms(inst)
    est_it = int(BUDGET * 1000.0 / dms) if dms > 0 else 0

    bw = schedule_baseline(inst).total_wait(inst)
    cp, cpt = run_timed(lambda: schedule_rcpsp(inst, time_limit_sec=BUDGET, random_seed=SEED))
    sa, sat = run_timed(lambda: schedule_sa(inst, seed=SEED, time_limit_sec=BUDGET))
    ga, gat = run_timed(lambda: schedule_ga(inst, seed=SEED, time_limit_sec=BUDGET, pop_size=GA_POP))
    cw, sw, gw = cp.total_wait(inst), sa.total_wait(inst), ga.total_wait(inst)

    cp_p = (cw - bw) / bw * 100
    sa_p = (sw - bw) / bw * 100
    ga_p = (gw - bw) / bw * 100
    best = min(cw, sw, gw)
    winner = "CP-SAT" if best == cw else ("SA" if best == sw else "GA")

    print(f"{N:>5}{T:>7}{dms:>8.1f}{est_it:>7}{bw:>11}{cw:>11}{cp_p:>6.1f}%{sw:>11}{sa_p:>6.1f}%{gw:>11}{ga_p:>6.1f}%  {winner:>7}   "
          f"{cpt:.0f}/{sat:.0f}/{gat:.0f}s", flush=True)
    rows.append({"N": N, "tasks": T, "decode_ms": round(dms, 2), "est_iters": est_it,
                 "baseline": bw, "cpsat": cw, "cp_pct": round(cp_p, 2),
                 "sa": sw, "sa_pct": round(sa_p, 2), "ga": gw, "ga_pct": round(ga_p, 2),
                 "winner": winner, "cp_wall": round(cpt, 1), "sa_wall": round(sat, 1), "ga_wall": round(gat, 1)})

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

# crossover summary
cross = next((r["N"] for r in rows if min(r["sa"], r["ga"]) < r["cpsat"]), None)
print(f"\n# crossover (first N where SA or GA beats CP-SAT): {cross}", flush=True)
print(f"# CSV -> {OUT_CSV}", flush=True)
print("# done", flush=True)
sys.exit(0)
