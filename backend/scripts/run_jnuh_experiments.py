"""
run_jnuh_experiments.py — JNUH surgical-suite experiment grid (ultragoal G004).

Grid (8 cells x 3 seeds x 5 algorithms = 120 runs):
  - Load axis (normal mode):  N in {20, 50, 100} x layout in {pool, block}
  - Crisis axis (N=50):       crisis x layout in {pool, block}

Algorithms: baseline / rcpsp (CP-SAT) / ga / sa / scil — all judged by the
same PINNED Sigma-wait via Schedule.total_wait (independent re-computation).
The objective is the unweighted total wait only (no priority weighting).

Budgets: every optimiser gets the same wall-clock cap (TIME_LIMIT_SEC) for a
fair "same stopwatch" comparison.  Seeds are fixed for reproducibility.

Columns (2026-06-11 decoder-speedup rerun):
  decode_ms     — per-decode benchmark time (ms) for the instance.
  iter_estimate — estimated GA generations / SA iterations achieved within the
                  budget, derived from wall_clock_sec and decode_ms.  Lets the
                  reader see whether a metaheuristic actually iterated.

Outputs (UTF-8):
  .omc/ultragoal/results/jnuh_results.json   — list of run dicts
  .omc/ultragoal/results/jnuh_results.csv    — same, flat CSV

Usage:
  python -m backend.scripts.run_jnuh_experiments
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

from backend.app.baseline import greedy_resource_schedule, schedule_baseline
from backend.app.data import generate_jnuh_instance
from backend.app.ga import schedule_ga
from backend.app.rcpsp import schedule_rcpsp
from backend.app.sa import schedule_sa
from backend.app.scil import schedule_scil
from backend.app import graph as _graph

TIME_LIMIT_SEC = 15.0
SEEDS = [42, 7, 99]
REGULAR_DAY_MIN = 480  # 8h regular operating day, for overtime KPI

OUT_DIR = Path(".omc/ultragoal/results")

SCENARIOS = []
for n in (20, 50, 100):
    for layout in ("pool", "block"):
        SCENARIOS.append(dict(n=n, layout=layout, crisis=False))
for layout in ("pool", "block"):
    SCENARIOS.append(dict(n=50, layout=layout, crisis=True))


def _benchmark_decode_ms(inst) -> float:
    """Measure single greedy_resource_schedule call time in ms (3-rep average)."""
    order = _graph.topological_order(inst)
    greedy_resource_schedule(inst, order)  # warm up
    t0 = time.perf_counter()
    reps = 3
    for _ in range(reps):
        greedy_resource_schedule(inst, order)
    return (time.perf_counter() - t0) / reps * 1000


def _run_algo(algo: str, inst, seed: int):
    if algo == "baseline":
        return schedule_baseline(inst)
    if algo == "rcpsp":
        return schedule_rcpsp(inst, time_limit_sec=TIME_LIMIT_SEC, random_seed=seed)
    if algo == "ga":
        return schedule_ga(inst, seed=seed, time_limit_sec=TIME_LIMIT_SEC)
    if algo == "sa":
        return schedule_sa(inst, seed=seed, time_limit_sec=TIME_LIMIT_SEC)
    if algo == "scil":
        return schedule_scil(
            inst, time_limit_sec=TIME_LIMIT_SEC, random_seed=seed, outer_rounds=2
        )
    raise ValueError(algo)


def _room_utilization(inst, sched) -> float:
    rooms = inst.resource_capacities.get("room", 1)
    makespan = sched.makespan()
    if makespan <= 0:
        return 0.0
    busy = sum(
        t.duration for t in inst.tasks.values() if t.resources.get("room", 0) > 0
    )
    return round(busy / (rooms * makespan), 4)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    t_start = time.perf_counter()
    total = len(SCENARIOS) * len(SEEDS) * 5
    done = 0

    for sc in SCENARIOS:
        for seed in SEEDS:
            inst = generate_jnuh_instance(
                n_patients=sc["n"],
                seed=seed,
                crisis=sc["crisis"],
                dedicated_blocks=(sc["layout"] == "block"),
            )
            # Benchmark decode time for this instance (used to estimate GA/SA iters)
            decode_ms = _benchmark_decode_ms(inst)

            for algo in ("baseline", "rcpsp", "ga", "sa", "scil"):
                t0 = time.perf_counter()
                try:
                    sched = _run_algo(algo, inst, seed)
                    sched.validate(inst)
                    err = ""
                except Exception as exc:  # record, never abort the grid
                    sched, err = None, f"{type(exc).__name__}: {exc}"
                wall = time.perf_counter() - t0
                done += 1

                if sched is not None:
                    wait = sched.total_wait(inst)
                    mk = sched.makespan()
                    # Estimate GA generations / SA iterations from wall time and
                    # decode speed.  GA: init = pop_size decodes, then each
                    # generation = pop_size decodes.  SA: each iteration = 1 decode.
                    # These are estimates; exact counts require modifying ga.py/sa.py.
                    if algo == "ga":
                        pop_size = 100  # default in ga.py
                        decode_time_s = decode_ms / 1000
                        remaining = wall - pop_size * decode_time_s
                        est_iters = max(0, int(remaining / (pop_size * decode_time_s)))
                        iter_note = f"~{est_iters} gen (decode {decode_ms:.0f}ms)"
                    elif algo == "sa":
                        decode_time_s = decode_ms / 1000
                        est_iters = max(0, int(wall / decode_time_s))
                        iter_note = f"~{est_iters} iters (decode {decode_ms:.0f}ms)"
                    else:
                        iter_note = ""
                    row = dict(
                        instance_id=inst.instance_id,
                        n=sc["n"], layout=sc["layout"],
                        mode="crisis" if sc["crisis"] else "normal",
                        seed=seed, algo=algo,
                        total_wait=wait,
                        avg_wait_per_task=round(wait / len(inst.tasks), 2),
                        avg_wait_per_patient=round(wait / sc["n"], 1),
                        decode_ms=round(decode_ms, 1),
                        iter_estimate=iter_note,
                        makespan=mk,
                        overtime_min=max(0, mk - REGULAR_DAY_MIN),
                        room_utilization=_room_utilization(inst, sched),
                        wall_clock_sec=round(wall, 2),
                        error="",
                    )
                else:
                    row = dict(
                        instance_id=inst.instance_id,
                        n=sc["n"], layout=sc["layout"],
                        mode="crisis" if sc["crisis"] else "normal",
                        seed=seed, algo=algo,
                        total_wait=None,
                        avg_wait_per_task=None,
                        avg_wait_per_patient=None,
                        decode_ms=round(decode_ms, 1),
                        iter_estimate="",
                        makespan=None,
                        overtime_min=None, room_utilization=None,
                        wall_clock_sec=round(wall, 2), error=err,
                    )
                rows.append(row)
                print(
                    f"[{done:3d}/{total}] {inst.instance_id} {algo:8s} "
                    f"wait={row['total_wait']} mk={row['makespan']} "
                    f"t={row['wall_clock_sec']}s {row['iter_estimate']} {err}",
                    flush=True,
                )

    json_path = OUT_DIR / "jnuh_results.json"
    json_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    csv_path = OUT_DIR / "jnuh_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    elapsed = time.perf_counter() - t_start
    failures = [r for r in rows if r["error"]]
    print(f"\nDONE: {len(rows)} runs in {elapsed:.0f}s -> {json_path}")
    if failures:
        print(f"FAILURES: {len(failures)}")
        for r in failures[:10]:
            print(" ", r["instance_id"], r["algo"], r["error"])
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
