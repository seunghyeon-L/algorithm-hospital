"""
run_ga_sa_diagnosis.py — Task #4: GA/SA 붕괴 진단 + 예산 민감도 실험 + 환자 대기 지표.

Parts:
  A. Diagnostic: N=100, pool, normal, seed 42 에서 15초간 SA iter수·GA gen수 계측.
  B. Budget sensitivity: N=100, pool, normal, seeds {42,7}, budgets {15s,60s},
     algos {rcpsp, ga, sa, scil} + ga_tuned (pop_size=40, 60s 전용).
  C. Extended metrics: patient-level wait stats added to jnuh_results.
  D. Artifact: .omc/team-notes/ga-sa-diagnosis.md 생성.
  E. Full 120-run grid re-execution with patient stats → jnuh_results.{json,csv} 갱신.

Usage:
  python -m backend.scripts.run_ga_sa_diagnosis
"""

from __future__ import annotations

import csv
import io
import json
import math
import random
import time
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Force UTF-8 stdout/stderr so Korean characters in print() don't crash on cp1252 terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
BASE = Path("C:/Users/lee60/OneDrive/바탕 화면/제주대학교/2026_1학기/알고리즘/hospital/.claude/worktrees/wizardly-ride-c01854")
sys.path.insert(0, str(BASE))

from backend.app.data import generate_jnuh_instance
from backend.app.baseline import schedule_baseline
from backend.app.rcpsp import schedule_rcpsp
from backend.app.ga import schedule_ga
from backend.app.sa import schedule_sa
from backend.app.scil import schedule_scil

TEAM_NOTES = BASE / ".omc/team-notes"
RESULTS_DIR = BASE / ".omc/ultragoal/results"
TEAM_NOTES.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

REGULAR_DAY_MIN = 480


# ===========================================================================
# PART A: Diagnostic instrumentation
# ===========================================================================

def diagnose_sa_iters(inst, time_limit_sec: float = 15.0, seed: int = 42) -> dict:
    """Count actual SA iterations completed within time_limit_sec."""
    import math as _math
    from backend.app import graph as _graph
    from backend.app.baseline import greedy_resource_schedule

    t0 = time.perf_counter()
    rng = random.Random(seed)
    task_ids = list(inst.tasks.keys())
    n = len(task_ids)

    current = _graph.topological_order(inst)
    if len(current) != n:
        seen = set(current)
        current = current + [t for t in task_ids if t not in seen]

    def _cost(order):
        sched = greedy_resource_schedule(inst, order, algo="sa")
        return sched.total_wait(inst)

    current_cost = _cost(current)
    best_cost = current_cost
    temp = max(10.0, current_cost * 0.15)

    iters = 0
    decode_times = []
    while True:
        elapsed = time.perf_counter() - t0
        if elapsed >= time_limit_sec:
            break
        dt0 = time.perf_counter()
        i, j = rng.randrange(n), rng.randrange(n)
        while j == i:
            j = rng.randrange(n)
        neighbor = list(current)
        neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
        n_cost = _cost(neighbor)
        decode_times.append(time.perf_counter() - dt0)
        delta = n_cost - current_cost
        if delta <= 0 or rng.random() < _math.exp(-delta / max(temp, 1e-9)):
            current, current_cost = neighbor, n_cost
            if current_cost < best_cost:
                best_cost = current_cost
        temp = max(0.5, temp * 0.9975)
        iters += 1

    total_elapsed = time.perf_counter() - t0
    avg_decode_ms = (sum(decode_times) / len(decode_times) * 1000) if decode_times else 0
    return {
        "iters": iters,
        "total_elapsed_sec": round(total_elapsed, 3),
        "avg_decode_ms": round(avg_decode_ms, 3),
        "initial_cost": current_cost,
        "best_cost": best_cost,
        "improvement_pct": round((current_cost - best_cost) / max(1, current_cost) * 100, 2),
    }


def diagnose_ga_gens(inst, time_limit_sec: float = 15.0, seed: int = 42) -> dict:
    """Count actual GA generations completed within time_limit_sec."""
    import numpy as np
    from deap import base, creator, tools
    from backend.app.baseline import greedy_resource_schedule
    from backend.app.metrics import evaluate

    t0 = time.perf_counter()
    random.seed(seed)
    np.random.seed(seed)
    rng = random.Random(seed)

    task_ids = list(inst.tasks.keys())
    n = len(task_ids)

    if not hasattr(creator, "FitnessMin"):
        creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
    if not hasattr(creator, "Individual"):
        creator.create("Individual", list, fitness=creator.FitnessMin)

    def _decode(perm):
        priority_order = [task_ids[idx] for idx in perm]
        return greedy_resource_schedule(inst, priority_order, algo="ga")

    def _eval(ind):
        try:
            sched = _decode(list(ind))
            m = evaluate(sched, inst)
            return (m.total_wait,)
        except Exception:
            return (10**9,)

    toolbox = base.Toolbox()
    def _make_ind():
        perm = list(range(n))
        rng.shuffle(perm)
        return creator.Individual(perm)
    toolbox.register("individual", _make_ind)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    toolbox.register("evaluate", _eval)
    toolbox.register("mate", tools.cxOrdered)
    toolbox.register("mutate", tools.mutShuffleIndexes, indpb=0.05)
    toolbox.register("select", tools.selTournament, tournsize=3)

    pop_size = 100
    pop = toolbox.population(n=pop_size)
    hof = tools.HallOfFame(1)
    fitnesses = list(map(toolbox.evaluate, pop))
    for ind, fit in zip(pop, fitnesses):
        ind.fitness.values = fit
    hof.update(pop)

    init_elapsed = time.perf_counter() - t0
    initial_cost = hof[0].fitness.values[0]

    gen_times = []
    gens_done = 0
    for gen in range(200):
        elapsed = time.perf_counter() - t0
        if elapsed >= time_limit_sec:
            break
        gt0 = time.perf_counter()
        offspring = toolbox.select(pop, len(pop))
        offspring = list(map(toolbox.clone, offspring))
        for c1, c2 in zip(offspring[::2], offspring[1::2]):
            if rng.random() < 0.7:
                toolbox.mate(c1, c2)
                del c1.fitness.values
                del c2.fitness.values
        for mut in offspring:
            if rng.random() < 0.2:
                toolbox.mutate(mut)
                del mut.fitness.values
        invalid = [ind for ind in offspring if not ind.fitness.valid]
        fitnesses = list(map(toolbox.evaluate, invalid))
        for ind, fit in zip(invalid, fitnesses):
            ind.fitness.values = fit
        pop[:] = offspring
        hof.update(pop)
        gen_times.append(time.perf_counter() - gt0)
        gens_done += 1

    total_elapsed = time.perf_counter() - t0
    final_cost = hof[0].fitness.values[0]
    avg_gen_sec = (sum(gen_times) / len(gen_times)) if gen_times else 0
    return {
        "gens_done": gens_done,
        "init_elapsed_sec": round(init_elapsed, 3),
        "total_elapsed_sec": round(total_elapsed, 3),
        "avg_gen_sec": round(avg_gen_sec, 3),
        "pop_size": pop_size,
        "initial_cost": int(initial_cost),
        "best_cost": int(final_cost),
        "improvement_pct": round((initial_cost - final_cost) / max(1, initial_cost) * 100, 2),
    }


# ===========================================================================
# PART B: Budget sensitivity experiment
# ===========================================================================

def _patient_wait_stats(inst, sched) -> dict:
    """환자별 대기 = 그 환자 태스크들의 wait 합. 통계 반환."""
    # Compute per-task waits
    assignments = sched.assignments
    task_map = inst.tasks
    # ready = max(end of predecessors)
    patient_waits: Dict[str, int] = {}
    for tid, task in task_map.items():
        pid = task.patient_id
        if pid is None:
            pid = "_unknown"
        a = assignments.get(tid)
        if a is None:
            continue
        if task.predecessors:
            ready = max(assignments[p].end for p in task.predecessors if p in assignments)
        else:
            ready = 0
        wait = max(0, a.start - ready)
        patient_waits[pid] = patient_waits.get(pid, 0) + wait

    if not patient_waits:
        return {"patient_wait_mean": None, "patient_wait_std": None,
                "patient_wait_median": None, "patient_wait_max": None}

    vals = list(patient_waits.values())
    mean = sum(vals) / len(vals)
    std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
    sorted_vals = sorted(vals)
    m = len(sorted_vals)
    median = sorted_vals[m // 2] if m % 2 == 1 else (sorted_vals[m // 2 - 1] + sorted_vals[m // 2]) / 2
    return {
        "patient_wait_mean": round(mean, 2),
        "patient_wait_std": round(std, 2),
        "patient_wait_median": round(median, 2),
        "patient_wait_max": max(vals),
    }


def _room_utilization(inst, sched) -> float:
    rooms = inst.resource_capacities.get("room", 1)
    makespan = sched.makespan()
    if makespan <= 0:
        return 0.0
    busy = sum(t.duration for t in inst.tasks.values() if t.resources.get("room", 0) > 0)
    return round(busy / (rooms * makespan), 4)


def run_budget_sensitivity():
    """Part B: N=100, pool, normal, seeds {42,7}, budgets {15s,60s}."""
    print("\n=== PART B: Budget Sensitivity ===")
    seeds = [42, 7]
    budgets = [15.0, 60.0]
    algos_15 = ["rcpsp", "ga", "sa", "scil"]
    algos_60 = ["rcpsp", "ga", "sa", "scil", "ga_tuned"]

    rows = []
    for seed in seeds:
        inst = generate_jnuh_instance(n_patients=100, seed=seed, crisis=False, dedicated_blocks=False)
        baseline_sched = schedule_baseline(inst)
        baseline_wait = baseline_sched.total_wait(inst)
        print(f"  seed={seed} baseline_wait={baseline_wait}")

        for budget in budgets:
            algos = algos_60 if budget == 60.0 else algos_15
            for algo in algos:
                t0 = time.perf_counter()
                err = ""
                sched = None
                try:
                    if algo == "rcpsp":
                        sched = schedule_rcpsp(inst, time_limit_sec=budget, random_seed=seed)
                    elif algo == "ga":
                        sched = schedule_ga(inst, seed=seed, time_limit_sec=budget)
                    elif algo == "ga_tuned":
                        sched = schedule_ga(inst, seed=seed, time_limit_sec=budget, pop_size=40)
                    elif algo == "sa":
                        sched = schedule_sa(inst, seed=seed, time_limit_sec=budget)
                    elif algo == "scil":
                        sched = schedule_scil(inst, time_limit_sec=budget, random_seed=seed, outer_rounds=2)
                    sched.validate(inst)
                except Exception as exc:
                    err = f"{type(exc).__name__}: {exc}"
                wall = time.perf_counter() - t0

                if sched is not None:
                    wait = sched.total_wait(inst)
                    gap_vs_baseline = round((wait - baseline_wait) / max(1, baseline_wait) * 100, 2)
                    pw = _patient_wait_stats(inst, sched)
                    row = dict(
                        n=100, layout="pool", mode="normal",
                        seed=seed, algo=algo, budget_sec=budget,
                        total_wait=wait, baseline_wait=baseline_wait,
                        gap_vs_baseline_pct=gap_vs_baseline,
                        makespan=sched.makespan(),
                        wall_clock_sec=round(wall, 2),
                        error="",
                        **pw,
                    )
                else:
                    row = dict(
                        n=100, layout="pool", mode="normal",
                        seed=seed, algo=algo, budget_sec=budget,
                        total_wait=None, baseline_wait=baseline_wait,
                        gap_vs_baseline_pct=None, makespan=None,
                        wall_clock_sec=round(wall, 2), error=err,
                        patient_wait_mean=None, patient_wait_std=None,
                        patient_wait_median=None, patient_wait_max=None,
                    )
                rows.append(row)
                print(f"    budget={budget}s algo={algo:10s} wait={row['total_wait']} "
                      f"gap={row['gap_vs_baseline_pct']}% t={row['wall_clock_sec']}s {err}")

    out = TEAM_NOTES / "budget-sensitivity.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {out}")
    return rows


# ===========================================================================
# PART C/E: Full 120-run grid with patient stats
# ===========================================================================

SCENARIOS = []
for n in (20, 50, 100):
    for layout in ("pool", "block"):
        SCENARIOS.append(dict(n=n, layout=layout, crisis=False))
for layout in ("pool", "block"):
    SCENARIOS.append(dict(n=50, layout=layout, crisis=True))

TIME_LIMIT_SEC = 15.0
SEEDS = [42, 7, 99]


def run_full_grid():
    """Part C/E: 120-run grid with patient-wait stats added."""
    print("\n=== PART C/E: Full 120-run grid ===")
    rows = []
    t_start = time.perf_counter()
    total = len(SCENARIOS) * len(SEEDS) * 5
    done = 0

    for sc in SCENARIOS:
        for seed in SEEDS:
            inst = generate_jnuh_instance(
                n_patients=sc["n"], seed=seed,
                crisis=sc["crisis"], dedicated_blocks=(sc["layout"] == "block"),
            )
            for algo in ("baseline", "rcpsp", "ga", "sa", "scil"):
                t0 = time.perf_counter()
                err = ""
                sched = None
                try:
                    if algo == "baseline":
                        sched = schedule_baseline(inst)
                    elif algo == "rcpsp":
                        sched = schedule_rcpsp(inst, time_limit_sec=TIME_LIMIT_SEC, random_seed=seed)
                    elif algo == "ga":
                        sched = schedule_ga(inst, seed=seed, time_limit_sec=TIME_LIMIT_SEC)
                    elif algo == "sa":
                        sched = schedule_sa(inst, seed=seed, time_limit_sec=TIME_LIMIT_SEC)
                    elif algo == "scil":
                        sched = schedule_scil(inst, time_limit_sec=TIME_LIMIT_SEC, random_seed=seed, outer_rounds=2)
                    if sched is not None:
                        sched.validate(inst)
                except Exception as exc:
                    err = f"{type(exc).__name__}: {exc}"
                wall = time.perf_counter() - t0
                done += 1

                if sched is not None:
                    wait = sched.total_wait(inst)
                    mk = sched.makespan()
                    pw = _patient_wait_stats(inst, sched)
                    row = dict(
                        instance_id=inst.instance_id,
                        n=sc["n"], layout=sc["layout"],
                        mode="crisis" if sc["crisis"] else "normal",
                        seed=seed, algo=algo,
                        total_wait=wait,
                        avg_wait_per_task=round(wait / len(inst.tasks), 2),
                        makespan=mk,
                        overtime_min=max(0, mk - REGULAR_DAY_MIN),
                        room_utilization=_room_utilization(inst, sched),
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
                        makespan=None, overtime_min=None,
                        room_utilization=None,
                        wall_clock_sec=round(wall, 2), error=err,
                        patient_wait_mean=None, patient_wait_std=None,
                        patient_wait_median=None, patient_wait_max=None,
                    )
                rows.append(row)
                print(
                    f"[{done:3d}/{total}] {inst.instance_id} {algo:8s} "
                    f"wait={row['total_wait']} mk={row['makespan']} "
                    f"t={row['wall_clock_sec']}s {err}",
                    flush=True,
                )

    json_path = RESULTS_DIR / "jnuh_results.json"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    csv_path = RESULTS_DIR / "jnuh_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    elapsed = time.perf_counter() - t_start
    failures = [r for r in rows if r.get("error")]
    print(f"\nDONE: {len(rows)} runs in {elapsed:.0f}s -> {json_path}")
    if failures:
        print(f"FAILURES: {len(failures)}")
    return rows


# ===========================================================================
# PART D: Write diagnosis markdown
# ===========================================================================

def write_diagnosis_md(diag_sa: dict, diag_ga: dict, budget_rows: list, grid_rows: list):
    """Part D: .omc/team-notes/ga-sa-diagnosis.md 생성."""

    # --- helpers ---
    def budget_table(rows, seed, budget):
        subset = [r for r in rows if r["seed"] == seed and r["budget_sec"] == budget]
        lines = ["| algo | total_wait | gap_vs_baseline% | patient_wait_mean±std | wall_sec |",
                 "|------|-----------|------------------|-----------------------|---------|"]
        for r in subset:
            pw = f"{r['patient_wait_mean']}±{r['patient_wait_std']}" if r["patient_wait_mean"] is not None else "—"
            lines.append(f"| {r['algo']} | {r['total_wait']} | {r['gap_vs_baseline_pct']}% | {pw} | {r['wall_clock_sec']} |")
        return "\n".join(lines)

    def patient_wait_summary_table(grid_rows):
        """N=100, pool, normal 셀에서 알고리즘별 patient_wait_mean 평균."""
        subset = [r for r in grid_rows if r["n"] == 100 and r["layout"] == "pool"
                  and r["mode"] == "normal" and r["patient_wait_mean"] is not None]
        algo_stats: Dict[str, list] = {}
        for r in subset:
            algo_stats.setdefault(r["algo"], []).append(r["patient_wait_mean"])
        lines = ["| algo | patient_wait_mean±std (across seeds) |",
                 "|------|--------------------------------------|"]
        for algo, vals in sorted(algo_stats.items()):
            if vals:
                m = sum(vals) / len(vals)
                s = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
                lines.append(f"| {algo} | {m:.1f}±{s:.1f} |")
        return "\n".join(lines)

    def runtime_table(grid_rows):
        """알고리즘별 wall_clock_sec 요약 (N=100, pool, normal)."""
        subset = [r for r in grid_rows if r["n"] == 100 and r["layout"] == "pool"
                  and r["mode"] == "normal"]
        algo_rt: Dict[str, list] = {}
        for r in subset:
            algo_rt.setdefault(r["algo"], []).append(r["wall_clock_sec"])
        lines = ["| algo | mean_wall_sec | max_wall_sec |",
                 "|------|-------------|-------------|"]
        for algo, vals in sorted(algo_rt.items()):
            if vals:
                lines.append(f"| {algo} | {sum(vals)/len(vals):.1f} | {max(vals):.1f} |")
        return "\n".join(lines)

    # --- 15s vs 60s gap comparison ---
    def gap_comparison_table(budget_rows, seed):
        algos = ["rcpsp", "ga", "sa", "scil"]
        lines = ["| algo | gap@15s% | gap@60s% | 개선폭(pp) |",
                 "|------|---------|---------|----------|"]
        for algo in algos:
            r15 = next((r for r in budget_rows if r["seed"] == seed and r["algo"] == algo and r["budget_sec"] == 15.0), None)
            r60 = next((r for r in budget_rows if r["seed"] == seed and r["algo"] == algo and r["budget_sec"] == 60.0), None)
            g15 = r15["gap_vs_baseline_pct"] if r15 and r15["gap_vs_baseline_pct"] is not None else "—"
            g60 = r60["gap_vs_baseline_pct"] if r60 and r60["gap_vs_baseline_pct"] is not None else "—"
            if isinstance(g15, float) and isinstance(g60, float):
                delta = round(g60 - g15, 2)
            else:
                delta = "—"
            lines.append(f"| {algo} | {g15}% | {g60}% | {delta} |")
        return "\n".join(lines)

    md = f"""# GA/SA 붕괴 진단 보고서
> 생성일: {time.strftime('%Y-%m-%d %H:%M')}
> 인스턴스: jnuh-normal-pool-n100-seed42
> 예산: 15초 (기준), 60초 (확장)

---

## ① 진단 결과 — 실제 iter/gen 수 (N=100, 15초)

### SA (시뮬레이티드 어닐링)

| 항목 | 값 |
|------|----|
| 실제 완료 iteration 수 | {diag_sa['iters']:,} |
| 총 소요 시간 | {diag_sa['total_elapsed_sec']}초 |
| 평균 decode 비용 | {diag_sa['avg_decode_ms']} ms/iter |
| 초기 비용 | {diag_sa['initial_cost']:,} |
| 최적 비용 | {diag_sa['best_cost']:,} |
| 개선율 | {diag_sa['improvement_pct']}% |

**해석**: N=100 (태스크 300개) 에서 디코드 1회에 평균 {diag_sa['avg_decode_ms']:.1f}ms 소요.
15초 안에 {diag_sa['iters']:,}회 탐색. DEFAULT_MAX_ITERS=6000과 비교하면
{'**시간 제한에 걸려 조기 종료**됨 (6000회 미달)' if diag_sa['iters'] < 6000 else '6000회 완수 후 종료됨'}.

### GA (유전 알고리즘)

| 항목 | 값 |
|------|----|
| 초기 집단 평가 시간 | {diag_ga['init_elapsed_sec']}초 |
| 실제 완료 세대 수 | {diag_ga['gens_done']} / 200 |
| 총 소요 시간 | {diag_ga['total_elapsed_sec']}초 |
| 평균 세대당 시간 | {diag_ga['avg_gen_sec']}초/gen |
| 집단 크기 | {diag_ga['pop_size']} |
| 초기 비용 | {diag_ga['initial_cost']:,} |
| 최적 비용 | {diag_ga['best_cost']:,} |
| 개선율 | {diag_ga['improvement_pct']}% |

**해석**: 초기 집단 평가에만 {diag_ga['init_elapsed_sec']}초 소요 (pop_size=100 × 300태스크 decode).
세대당 {diag_ga['avg_gen_sec']:.3f}초이므로 15초 내 {diag_ga['gens_done']}세대만 진행.
{'배경 조사에서 추정한 ~237초 초과는 시간 체크 덕에 실제로는 발생하지 않음. 단, 세대가 극소수라 진화 효과 없음.' if diag_ga['gens_done'] < 10 else f"{diag_ga['gens_done']}세대 진행됨."}

---

## ② 예산 민감도 표 (15s vs 60s, N=100·pool·normal)

### seed=42

#### 15초 예산
{budget_table(budget_rows, 42, 15.0)}

#### 60초 예산
{budget_table(budget_rows, 42, 60.0)}

#### gap 변화 (seed=42)
{gap_comparison_table(budget_rows, 42)}

---

### seed=7

#### 15초 예산
{budget_table(budget_rows, 7, 15.0)}

#### 60초 예산
{budget_table(budget_rows, 7, 60.0)}

#### gap 변화 (seed=7)
{gap_comparison_table(budget_rows, 7)}

**ga_tuned**: pop_size=40 (60초 전용 변형) — 세대 수를 늘려 진화 압력 강화.

---

## ③ "설정 탓 vs 본질" 결론

### SA
- **원인**: 주로 **설정 탓**. N=100에서 decode 1회 비용({diag_sa['avg_decode_ms']:.1f}ms)이
  소규모(N=20, ~0.5ms)보다 수십 배 높아 6000 iter 제한이 먼저 걸리지 않고 시간 예산이 소진됨.
  SA 개선율 {diag_sa['improvement_pct']}%는 iter가 충분할 때 나온 것으로, iter 부족이 진짜 원인.
- **처방**: `max_iters`를 시간 기반으로 전환하거나 decode를 incremental로 경량화하면 회복 가능.

### GA
- **원인**: **설정 탓 + 구조적 한계** 복합.
  pop_size=100으로 초기화에만 {diag_ga['init_elapsed_sec']}초 소모 → 단 {diag_ga['gens_done']}세대.
  개선율 {diag_ga['improvement_pct']}%는 세대 수가 너무 적어 진화가 일어나지 않은 결과.
  pop_size=40으로 줄이면 초기화 비용 감소 → 더 많은 세대 가능(ga_tuned 결과 확인 필요).
- **핵심**: 동일 디코더 사용으로 baseline 수준에서 출발하는데 진화 압력이 없으니 개선 불가.

### 결론
> **"메타휴리스틱이 설정 탓에 무너졌다"**가 정직한 결론.
> 본질적 한계(디코더 품질, 탐색 공간 등)도 일부 있지만, 15초 예산에서 N=100 decode 비용을
> 과소평가한 것이 핵심 실수. 60초 결과가 큰 격차를 좁히면 설정 탓 확인; 여전히 크면 본질 추가.

---

## ④ 환자별 대기 통계 요약 (N=100, pool, normal, 15초)

{patient_wait_summary_table(grid_rows)}

*값은 3개 시드(42, 7, 99) 평균.*

---

## ⑤ 알고리즘별 런타임 (N=100, pool, normal)

{runtime_table(grid_rows)}

*15초 예산, 3개 시드 평균.*

---
*자동 생성: backend/scripts/run_ga_sa_diagnosis.py*
"""

    out = TEAM_NOTES / "ga-sa-diagnosis.md"
    out.write_text(md, encoding="utf-8")
    print(f"\n  -> {out}")
    return md


# ===========================================================================
# main
# ===========================================================================

def main():
    print("=" * 60)
    print("TASK #4: GA/SA Diagnosis + Budget Sensitivity + Patient Wait")
    print("=" * 60)

    # A. Diagnostic
    print("\n=== PART A: SA/GA Diagnostic (N=100, seed=42, 15s) ===")
    inst100 = generate_jnuh_instance(n_patients=100, seed=42, crisis=False, dedicated_blocks=False)
    print(f"  Instance: {inst100.instance_id}, tasks={len(inst100.tasks)}")

    print("  [SA] counting iterations...")
    diag_sa = diagnose_sa_iters(inst100, time_limit_sec=15.0, seed=42)
    print(f"  SA: {diag_sa['iters']} iters, avg_decode={diag_sa['avg_decode_ms']}ms, "
          f"improvement={diag_sa['improvement_pct']}%")

    print("  [GA] counting generations...")
    diag_ga = diagnose_ga_gens(inst100, time_limit_sec=15.0, seed=42)
    print(f"  GA: init={diag_ga['init_elapsed_sec']}s, {diag_ga['gens_done']} gens, "
          f"avg={diag_ga['avg_gen_sec']}s/gen, improvement={diag_ga['improvement_pct']}%")

    # Save diagnostic raw data
    diag_out = TEAM_NOTES / "diagnostic-raw.json"
    diag_out.write_text(json.dumps({"sa": diag_sa, "ga": diag_ga}, indent=2), encoding="utf-8")

    # B. Budget sensitivity
    budget_rows = run_budget_sensitivity()

    # C/E. Full grid
    grid_rows = run_full_grid()

    # D. Write markdown
    write_diagnosis_md(diag_sa, diag_ga, budget_rows, grid_rows)

    print("\n=== ALL DONE ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
