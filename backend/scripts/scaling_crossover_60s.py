"""
scaling_crossover_60s.py — Same crossover scan but with a 60s budget, and we
also report ACTUAL wall-clock runtime of each algorithm.

Questions:
  1. Does a 4x bigger budget (15s -> 60s) push the CP-vs-SA/GA crossover to
     larger N (CP stays dominant longer)?
  2. How long does each algorithm actually run?  CP-SAT and SA respect the cap;
     GA checks time only between generations, so it can overshoot — especially
     at large N where one generation (= pop_size decodes) is expensive.

Improvement is vs the greedy baseline (more negative = better).
"""
from __future__ import annotations
import sys, time
from backend.app.data import generate_jnuh_instance
from backend.app.baseline import schedule_baseline
from backend.app.rcpsp import schedule_rcpsp
from backend.app.sa import schedule_sa
from backend.app.ga import schedule_ga

BUDGET = 60.0
SEED = 42
NS = [100, 200, 300, 400, 600]


def timed(fn):
    t0 = time.perf_counter()
    sched = fn()
    return sched, time.perf_counter() - t0


print(f"budget={BUDGET}s  seed={SEED}   (improvement vs greedy baseline; runtime in seconds)")
print(f"{'N':>5} {'tasks':>6} {'base':>10} "
      f"{'CP%':>7} {'CPs':>5}  {'SA%':>7} {'SAs':>5}  {'GA%':>7} {'GAs':>6}  winner")
for N in NS:
    inst = generate_jnuh_instance(n_patients=N, seed=SEED)
    nt = len(inst.tasks)
    base = schedule_baseline(inst); bw = base.total_wait(inst)

    cp, cp_t = timed(lambda: schedule_rcpsp(inst, time_limit_sec=BUDGET, random_seed=SEED))
    sa, sa_t = timed(lambda: schedule_sa(inst, seed=SEED, time_limit_sec=BUDGET))
    ga, ga_t = timed(lambda: schedule_ga(inst, seed=SEED, time_limit_sec=BUDGET))

    cw, sw, gw = cp.total_wait(inst), sa.total_wait(inst), ga.total_wait(inst)
    cp_p = (cw - bw) / bw * 100
    sa_p = (sw - bw) / bw * 100
    ga_p = (gw - bw) / bw * 100
    best = min(cw, sw, gw)
    winner = "CP" if best == cw else ("SA" if best == sw else "GA")
    print(f"{N:>5} {nt:>6} {bw:>10} "
          f"{cp_p:>6.1f}% {cp_t:>4.0f}s  {sa_p:>6.1f}% {sa_t:>4.0f}s  "
          f"{ga_p:>6.1f}% {ga_t:>5.0f}s  {winner}", flush=True)

sys.exit(0)
