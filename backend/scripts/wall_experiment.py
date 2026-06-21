# -*- coding: utf-8 -*-
"""Push the metaheuristic 'wall' by raising the evaluation budget (time).

The wall = the N beyond which SA/GA run out of iterations relative to the
search-space size and degrade toward (or below) the greedy baseline.

Lever = wall-clock budget (directly buys iterations: iters ≈ budget / decode_time,
and decode_time grows ~O(T²)=O(N²), so the wall scales ~sqrt(budget)).

We measure SA% and GA% (vs greedy baseline) at budgets 60s and 120s across N,
so the wall location at each budget can be read off. (15s data already exists.)
All native (numba decoder). seed=42.
"""
from __future__ import annotations
import sys, csv, os

from backend.app.data import generate_jnuh_instance
from backend.app.baseline import schedule_baseline
from backend.scripts.numba_engine import sa_native, ga_native, verify

SEED = 42
OUT = os.path.join(os.path.dirname(__file__), "_wall_results_ga.csv")

# (algo_name, fn, budget_sec, [N...])  — GA re-run (SA already captured in _wall_results.csv)
CONFIGS = [
    ("GA", ga_native, 60,  [300, 450, 600, 800]),
    ("GA", ga_native, 120, [600, 900, 1200]),
]

if not verify():
    print("ABORT: decoder mismatch", flush=True)
    sys.exit(1)

rows = []
for name, fn, budget, NS in CONFIGS:
    print(f"\n# {name} | budget={budget}s | (% vs greedy baseline; more negative = better)", flush=True)
    print(f"{'N':>5}{'tasks':>7}{'base':>13}{'val':>13}{'%':>8}{'iters':>9}", flush=True)
    for N in NS:
        inst = generate_jnuh_instance(n_patients=N, seed=SEED)
        T = len(inst.tasks)
        bw = schedule_baseline(inst).total_wait(inst)
        val, it, wall = fn(inst, seed=SEED, budget=budget)
        pct = (val - bw) / bw * 100.0
        print(f"{N:>5}{T:>7}{bw:>13}{val:>13}{pct:>7.1f}%{it:>9}", flush=True)
        rows.append({"algo": name, "budget": budget, "N": N, "tasks": T,
                     "baseline": bw, "value": val, "pct": round(pct, 2), "iters": it})
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)

print(f"\n# CSV -> {OUT}", flush=True)
print("# done", flush=True)
