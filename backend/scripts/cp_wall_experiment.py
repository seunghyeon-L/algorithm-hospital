# -*- coding: utf-8 -*-
"""CP-SAT wall vs time budget (1min ~ 10min).

At 15s, CP-SAT stops improving over the greedy baseline at ~N=150 (it returns
the warm-start). Question: as we raise the budget (60s, 300s=5min, 600s=10min),
how far does CP-SAT's 'still improving' wall move?

CP-SAT is anytime (best feasible within budget) + warm-started from baseline, so
it never does worse than baseline; the wall = the N where its improvement drops
toward 0% within the budget.

Fast-first ordering (low budgets before high) so partial data is useful if the
run is interrupted. seed=42. CP-SAT uses 8 workers -> run ALONE (no other CPU
load) for fair timing.
"""
from __future__ import annotations
import sys, csv, os, time

from backend.app.data import generate_jnuh_instance
from backend.app.baseline import schedule_baseline
from backend.app.rcpsp import schedule_rcpsp

SEED = 42
OUT = os.path.join(os.path.dirname(__file__), "_cp_wall_results.csv")

# (budget_sec, [N...]) — N lists bracket the expected wall at each budget
CONFIGS = [
    (60,  [150, 250, 350]),
    (300, [250, 400, 550]),
    (600, [400, 600]),
]

rows = []
print("# CP-SAT wall vs time budget | (% vs greedy baseline; more negative = better) | seed=42", flush=True)
for budget, NS in CONFIGS:
    print(f"\n# CP-SAT | budget={budget}s ({budget // 60}min)", flush=True)
    print(f"{'N':>5}{'tasks':>7}{'base':>13}{'cp':>13}{'%':>8}{'wall':>8}", flush=True)
    for N in NS:
        inst = generate_jnuh_instance(n_patients=N, seed=SEED)
        T = len(inst.tasks)
        bw = schedule_baseline(inst).total_wait(inst)
        t0 = time.perf_counter()
        cw = schedule_rcpsp(inst, time_limit_sec=budget, random_seed=SEED).total_wait(inst)
        wall = time.perf_counter() - t0
        pct = (cw - bw) / bw * 100.0
        print(f"{N:>5}{T:>7}{bw:>13}{cw:>13}{pct:>7.1f}%{wall:>7.0f}s", flush=True)
        rows.append({"budget": budget, "N": N, "tasks": T, "baseline": bw,
                     "cp": cw, "pct": round(pct, 2), "wall_sec": round(wall, 1)})
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)

print(f"\n# CSV -> {OUT}", flush=True)
print("# done", flush=True)
