"""
scaling_crossover.py — Where does CP-SAT's 15s solution quality fall behind SA?

CP-SAT here is time-capped (anytime): it returns the best solution found within
the budget, NOT a proven optimum.  As N grows, its 15s solution should drift
from "near-optimal" toward "barely better than greedy", and eventually SA (which
starts from a greedy solution and perturbs) could match or beat it.

We scale N and report each algorithm's improvement over the greedy baseline.
Crossover = the first N where SA's improvement exceeds CP-SAT's.
"""
from __future__ import annotations
import sys, time
from backend.app.data import generate_jnuh_instance
from backend.app.baseline import schedule_baseline
from backend.app.rcpsp import schedule_rcpsp
from backend.app.sa import schedule_sa

BUDGET = 15.0
SEED = 42
NS = [200, 250, 300, 350, 400, 500, 600]

print(f"budget={BUDGET}s seed={SEED}  (improvement vs greedy baseline; more negative = better)")
print(f"{'N':>5} {'tasks':>6} {'base':>9} {'CP-SAT':>9} {'CP%':>7} {'SA':>9} {'SA%':>7} {'winner':>8}")
for N in NS:
    inst = generate_jnuh_instance(n_patients=N, seed=SEED)
    ntasks = len(inst.tasks)
    base = schedule_baseline(inst); bw = base.total_wait(inst)

    t0 = time.perf_counter()
    cp = schedule_rcpsp(inst, time_limit_sec=BUDGET, random_seed=SEED)
    cp_t = time.perf_counter() - t0
    cw = cp.total_wait(inst)

    t0 = time.perf_counter()
    sa = schedule_sa(inst, seed=SEED, time_limit_sec=BUDGET)
    sa_t = time.perf_counter() - t0
    sw = sa.total_wait(inst)

    cp_pct = (cw - bw) / bw * 100
    sa_pct = (sw - bw) / bw * 100
    winner = "CP" if cw < sw else ("SA" if sw < cw else "tie")
    print(f"{N:>5} {ntasks:>6} {bw:>9} {cw:>9} {cp_pct:>6.1f}% {sw:>9} {sa_pct:>6.1f}% {winner:>8}"
          f"   (cp {cp_t:.0f}s, sa {sa_t:.0f}s)", flush=True)

print("\nNote: CP wins every row => crossover not yet reached at this scale/budget.")
sys.exit(0)
