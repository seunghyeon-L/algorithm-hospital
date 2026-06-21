"""
add_patient_stats.py — Re-run 120-grid adding patient wait columns.
GA at N=100 is skipped (takes ~250s each); original result is kept with null patient stats.
"""
from __future__ import annotations
import csv, io, json, sys, time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE = Path("C:/Users/lee60/OneDrive/바탕 화면/제주대학교/2026_1학기/알고리즘/hospital/.claude/worktrees/wizardly-ride-c01854")
sys.path.insert(0, str(BASE))

from backend.app.data import generate_jnuh_instance
from backend.app.baseline import schedule_baseline
from backend.app.rcpsp import schedule_rcpsp
from backend.app.ga import schedule_ga
from backend.app.sa import schedule_sa
from backend.app.scil import schedule_scil

OUT_DIR = BASE / ".omc/ultragoal/results"
TIME_LIMIT = 15.0
SEEDS = [42, 7, 99]
REGULAR_DAY_MIN = 480

SCENARIOS = []
for n in (20, 50, 100):
    for layout in ("pool", "block"):
        SCENARIOS.append(dict(n=n, layout=layout, crisis=False))
for layout in ("pool", "block"):
    SCENARIOS.append(dict(n=50, layout=layout, crisis=True))


def patient_wait_stats(inst, sched):
    assignments = sched.assignments
    patient_waits = {}
    for tid, task in inst.tasks.items():
        pid = task.patient_id or "_unknown"
        a = assignments.get(tid)
        if a is None:
            continue
        if task.predecessors:
            ready = max(assignments[p].end for p in task.predecessors if p in assignments)
        else:
            ready = 0
        wait = max(0, a.start - ready)
        patient_waits[pid] = patient_waits.get(pid, 0) + wait
    vals = list(patient_waits.values())
    if not vals:
        return {k: None for k in ("patient_wait_mean", "patient_wait_std", "patient_wait_median", "patient_wait_max")}
    mean = sum(vals) / len(vals)
    std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
    sv = sorted(vals)
    m = len(sv)
    median = sv[m // 2] if m % 2 == 1 else (sv[m // 2 - 1] + sv[m // 2]) / 2
    return {
        "patient_wait_mean": round(mean, 1),
        "patient_wait_std": round(std, 1),
        "patient_wait_median": round(median, 1),
        "patient_wait_max": max(vals),
    }


def room_utilization(inst, sched):
    rooms = inst.resource_capacities.get("room", 1)
    mk = sched.makespan()
    if mk <= 0:
        return 0.0
    busy = sum(t.duration for t in inst.tasks.values() if t.resources.get("room", 0) > 0)
    return round(busy / (rooms * mk), 4)


def main():
    # Load original results for GA N=100 (we won't re-run those)
    orig_path = OUT_DIR / "jnuh_results.json"
    orig = json.loads(orig_path.read_text(encoding="utf-8"))
    ga_n100_orig = {
        (r["instance_id"], r["seed"]): r
        for r in orig
        if r.get("algo") == "ga" and r.get("n") == 100
    }

    rows = []
    done = 0
    total = len(SCENARIOS) * len(SEEDS) * 5

    for sc in SCENARIOS:
        for seed in SEEDS:
            inst = generate_jnuh_instance(
                n_patients=sc["n"], seed=seed,
                crisis=sc["crisis"], dedicated_blocks=(sc["layout"] == "block"),
            )
            for algo in ("baseline", "rcpsp", "ga", "sa", "scil"):
                done += 1
                # Skip GA N=100: use original result with null patient stats
                if algo == "ga" and sc["n"] == 100:
                    orig_row = ga_n100_orig.get((inst.instance_id, seed), {})
                    row = dict(orig_row)
                    row["patient_wait_mean"] = None
                    row["patient_wait_std"] = None
                    row["patient_wait_median"] = None
                    row["patient_wait_max"] = None
                    rows.append(row)
                    print(f"[{done:3d}/{total}] SKIP(GA_N100) {inst.instance_id} seed={seed}", flush=True)
                    continue

                t0 = time.perf_counter()
                sched = None
                err = ""
                try:
                    if algo == "baseline":
                        sched = schedule_baseline(inst)
                    elif algo == "rcpsp":
                        sched = schedule_rcpsp(inst, time_limit_sec=TIME_LIMIT, random_seed=seed)
                    elif algo == "ga":
                        sched = schedule_ga(inst, seed=seed, time_limit_sec=TIME_LIMIT)
                    elif algo == "sa":
                        sched = schedule_sa(inst, seed=seed, time_limit_sec=TIME_LIMIT)
                    elif algo == "scil":
                        sched = schedule_scil(inst, time_limit_sec=TIME_LIMIT, random_seed=seed, outer_rounds=2)
                    if sched is not None:
                        sched.validate(inst)
                except Exception as exc:
                    err = f"{type(exc).__name__}: {exc}"
                wall = time.perf_counter() - t0

                if sched is not None:
                    wait = sched.total_wait(inst)
                    mk = sched.makespan()
                    pw = patient_wait_stats(inst, sched)
                    row = dict(
                        instance_id=inst.instance_id,
                        n=sc["n"], layout=sc["layout"],
                        mode="crisis" if sc["crisis"] else "normal",
                        seed=seed, algo=algo,
                        total_wait=wait,
                        avg_wait_per_task=round(wait / len(inst.tasks), 2),
                        makespan=mk,
                        overtime_min=max(0, mk - REGULAR_DAY_MIN),
                        room_utilization=room_utilization(inst, sched),
                        wall_clock_sec=round(wall, 2),
                        error="",
                        **pw,
                    )
                else:
                    row = dict(
                        instance_id=inst.instance_id,
                        n=sc["n"], layout=sc["layout"],
                        mode="crisis" if sc["crisis"] else "normal",
                        seed=seed, algo=algo,
                        total_wait=None, avg_wait_per_task=None,
                        makespan=None, overtime_min=None, room_utilization=None,
                        wall_clock_sec=round(wall, 2), error=err,
                        patient_wait_mean=None, patient_wait_std=None,
                        patient_wait_median=None, patient_wait_max=None,
                    )
                rows.append(row)
                print(
                    f"[{done:3d}/{total}] {inst.instance_id} {algo:8s} "
                    f"wait={row['total_wait']} t={row['wall_clock_sec']}s {err}",
                    flush=True,
                )

    json_path = OUT_DIR / "jnuh_results.json"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    csv_path = OUT_DIR / "jnuh_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    failures = [r for r in rows if r.get("error") and "skipped" not in r.get("error", "")]
    print(f"\nDONE: {len(rows)} rows written. Failures: {len(failures)}", flush=True)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
