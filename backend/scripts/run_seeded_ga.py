# -*- coding: utf-8 -*-
"""Baseline-seeded GA vs random-init GA (native numba engine).

Question: does seeding ONE baseline (greedy/topological) individual into the
initial population fix GA's large-N collapse (where random-init GA ends WORSE
than baseline)? With elitism, a seeded GA can never end worse than the baseline
it started from — like SA, which also starts from the baseline order.

15s budget, seed=42, both variants on the SAME instances for a clean head-to-head.
"""
from __future__ import annotations
import sys, csv, os

from backend.app.data import generate_jnuh_instance
from backend.app.baseline import schedule_baseline
from backend.scripts.numba_engine import ga_native, verify

SEED = 42
BUDGET = 15.0
N_LIST = [100, 150, 200, 300, 400, 500, 700, 1000]
OUT = os.path.join(os.path.dirname(__file__), "_seeded_ga.csv")

if not verify():
    print("ABORT: decoder mismatch", flush=True)
    sys.exit(1)

print(f"# GA random-init vs baseline-seeded | budget={BUDGET}s seed={SEED} (% vs greedy baseline)", flush=True)
print(f"{'N':>5}{'tasks':>7}{'base':>13}{'GArand%':>9}{'GAseed%':>9}{'winner':>9}", flush=True)
rows = []
for N in N_LIST:
    inst = generate_jnuh_instance(n_patients=N, seed=SEED)
    T = len(inst.tasks)
    bw = schedule_baseline(inst).total_wait(inst)
    r, _, _ = ga_native(inst, seed=SEED, budget=BUDGET, seed_baseline=False)
    s, _, _ = ga_native(inst, seed=SEED, budget=BUDGET, seed_baseline=True)
    rp = (r - bw) / bw * 100.0
    sp = (s - bw) / bw * 100.0
    winner = "seed" if s < r else ("rand" if r < s else "tie")
    print(f"{N:>5}{T:>7}{bw:>13}{rp:>8.1f}%{sp:>8.1f}%{winner:>9}", flush=True)
    rows.append({"N": N, "tasks": T, "base": bw, "ga_rand_pct": round(rp, 2),
                 "ga_seed_pct": round(sp, 2), "winner": winner})
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

print(f"\n# CSV -> {OUT}", flush=True)
print("# done", flush=True)
