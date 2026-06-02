"""
run_generalization.py — 확장요소 B: 일반화 검증 스크립트.

여러 규모/시나리오(n_tasks, seed, edge_prob, 자원분포)에서
baseline / rcpsp / ga 세 알고리즘을 동일 인스턴스에 실행하고
Σwait 개선 부호(>0)가 데이터셋 전반에서 일관하는지 검증한다.

합격 조건 (반증 가능):
  - RCPSP: 모든 시나리오에서 baseline 대비 Σwait 개선 > 0   (엄격)
  - GA:    개선 부호가 일관되는지 보고; 미달 시 정직하게 표기  (완화)

Usage (project root):
  python -m backend.scripts.run_generalization

또는 backend/ 디렉터리에서:
  python -m scripts.run_generalization

Options (environment variables):
  RCPSP_TIME_LIMIT  — CP-SAT solver time limit per instance (default 20s)
  GA_TIME_LIMIT     — GA wall-clock budget per instance (default 20s)
  QUICK             — set to '1' for a quick smoke-test run (small n, 1 gen)
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# sys.path bootstrap — must run before any project imports.
# Works whether this file is run as:
#   python backend/scripts/run_generalization.py     (project root)
#   python -m backend.scripts.run_generalization     (project root, -m)
#   python -m scripts.run_generalization             (backend/ cwd)
# In all cases we ensure the project root (hospital/) is on sys.path so
# that `from backend.app.X import ...` always resolves.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))          # .../backend/scripts
_ROOT = os.path.dirname(os.path.dirname(_HERE))             # .../hospital
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Windows consoles default to cp1252, which cannot encode 'Σ' and other
# symbols used in the report table.  Force UTF-8 stdout (best-effort).
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from backend.app.data import generate_instance              # noqa: E402
from backend.app.baseline import schedule_baseline          # noqa: E402
from backend.app.rcpsp import schedule_rcpsp                # noqa: E402
from backend.app.ga import schedule_ga                      # noqa: E402
from backend.app.metrics import evaluate                    # noqa: E402


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RCPSP_TIME_LIMIT: float = float(os.environ.get("RCPSP_TIME_LIMIT", "10"))
GA_TIME_LIMIT: float    = float(os.environ.get("GA_TIME_LIMIT", "10"))
QUICK: bool             = os.environ.get("QUICK", "0") == "1"

# GA parameters (lighter for generalization sweep; same budget as RCPSP)
GA_POP_SIZE = 20 if QUICK else 60
GA_N_GEN    = 3  if QUICK else 60
GA_SEED     = 42  # fixed for reproducibility


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------
# Each scenario is a dict of kwargs for generate_instance().
# We test three axes of variation:
#   A) scale (n_tasks: 15 / 30 / 50)
#   B) density (edge_prob: sparse 0.15 / medium 0.25 / dense 0.40)
#   C) resource pressure (n_rooms: tight 2 / normal 3 / relaxed 5)
#
# Total: 9 synthetic scenarios + a note slot for PSPLIB if a .sm file exists.
# ---------------------------------------------------------------------------

_QUICK_SCENARIOS = [
    dict(label="quick-n10-seed42",  n_tasks=10, seed=42, n_rooms=3, n_staff=5, edge_prob=0.25),
    dict(label="quick-n15-seed7",   n_tasks=15, seed=7,  n_rooms=3, n_staff=5, edge_prob=0.25),
]

_FULL_SCENARIOS = [
    # --- Scale axis ---
    dict(label="scale-n15-seed42",  n_tasks=15, seed=42, n_rooms=3, n_staff=5, edge_prob=0.25),
    dict(label="scale-n30-seed42",  n_tasks=30, seed=42, n_rooms=3, n_staff=5, edge_prob=0.25),
    dict(label="scale-n50-seed42",  n_tasks=50, seed=42, n_rooms=3, n_staff=5, edge_prob=0.25),
    # --- Density axis ---
    dict(label="density-sparse",    n_tasks=30, seed=1,  n_rooms=3, n_staff=5, edge_prob=0.10),
    dict(label="density-medium",    n_tasks=30, seed=1,  n_rooms=3, n_staff=5, edge_prob=0.25),
    dict(label="density-dense",     n_tasks=30, seed=1,  n_rooms=3, n_staff=5, edge_prob=0.45),
    # --- Resource pressure axis ---
    dict(label="rooms-tight-n30",   n_tasks=30, seed=2,  n_rooms=2, n_staff=5, edge_prob=0.25),
    dict(label="rooms-normal-n30",  n_tasks=30, seed=2,  n_rooms=3, n_staff=5, edge_prob=0.25),
    dict(label="rooms-relaxed-n30", n_tasks=30, seed=2,  n_rooms=5, n_staff=5, edge_prob=0.25),
    # --- Different seeds (reproducibility cross-check) ---
    dict(label="seed-99-n35",       n_tasks=35, seed=99, n_rooms=3, n_staff=5, edge_prob=0.25),
    dict(label="seed-7-n40",        n_tasks=40, seed=7,  n_rooms=3, n_staff=5, edge_prob=0.30),
]

SCENARIOS = _QUICK_SCENARIOS if QUICK else _FULL_SCENARIOS


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ScenarioResult:
    label: str
    n_tasks: int
    baseline_wait: int
    rcpsp_wait: int
    ga_wait: int
    rcpsp_pct: float        # % improvement of rcpsp vs baseline
    ga_pct: float           # % improvement of ga vs baseline
    rcpsp_wall: float
    ga_wall: float
    baseline_wall: float
    rcpsp_improved: bool    # rcpsp_wait < baseline_wait (strict)
    ga_improved: bool       # ga_wait < baseline_wait


# ---------------------------------------------------------------------------
# Run one scenario
# ---------------------------------------------------------------------------

def run_scenario(scenario: dict) -> ScenarioResult:
    label    = scenario["label"]
    n_tasks  = scenario["n_tasks"]
    seed     = scenario["seed"]
    n_rooms  = scenario.get("n_rooms", 3)
    n_staff  = scenario.get("n_staff", 5)
    edge_prob= scenario.get("edge_prob", 0.25)

    print(f"  [{label}] generating instance (n={n_tasks}, seed={seed}, "
          f"rooms={n_rooms}, edge_prob={edge_prob:.2f}) ...", flush=True)

    inst = generate_instance(
        n_tasks=n_tasks, seed=seed,
        n_rooms=n_rooms, n_staff=n_staff,
        edge_prob=edge_prob,
    )

    # --- baseline ---
    t0 = time.perf_counter()
    sched_b = schedule_baseline(inst)
    baseline_wall = time.perf_counter() - t0
    m_b = evaluate(sched_b, inst)

    # --- rcpsp ---
    print(f"  [{label}] running RCPSP (limit={RCPSP_TIME_LIMIT}s) ...", flush=True)
    try:
        sched_r = schedule_rcpsp(inst, time_limit_sec=RCPSP_TIME_LIMIT, random_seed=42)
        m_r = evaluate(sched_r, inst, baseline_wait=m_b.total_wait)
        rcpsp_wait = m_r.total_wait
        rcpsp_wall = sched_r.wall_clock_sec
        rcpsp_pct  = m_r.pct_improvement_vs_baseline or 0.0
    except Exception as exc:
        print(f"  [{label}] RCPSP FAILED: {exc}", flush=True)
        rcpsp_wait = m_b.total_wait  # treat as no improvement
        rcpsp_wall = RCPSP_TIME_LIMIT
        rcpsp_pct  = 0.0

    # --- ga ---
    print(f"  [{label}] running GA (limit={GA_TIME_LIMIT}s, "
          f"pop={GA_POP_SIZE}, gen={GA_N_GEN}) ...", flush=True)
    try:
        sched_g = schedule_ga(
            inst, seed=GA_SEED,
            pop_size=GA_POP_SIZE, n_gen=GA_N_GEN,
            time_limit_sec=GA_TIME_LIMIT,
        )
        m_g = evaluate(sched_g, inst, baseline_wait=m_b.total_wait)
        ga_wait = m_g.total_wait
        ga_wall = sched_g.wall_clock_sec
        ga_pct  = m_g.pct_improvement_vs_baseline or 0.0
    except Exception as exc:
        print(f"  [{label}] GA FAILED: {exc}", flush=True)
        ga_wait = m_b.total_wait
        ga_wall = GA_TIME_LIMIT
        ga_pct  = 0.0

    return ScenarioResult(
        label=label,
        n_tasks=n_tasks,
        baseline_wait=m_b.total_wait,
        rcpsp_wait=rcpsp_wait,
        ga_wait=ga_wait,
        rcpsp_pct=rcpsp_pct,
        ga_pct=ga_pct,
        rcpsp_wall=rcpsp_wall,
        ga_wall=ga_wall,
        baseline_wall=baseline_wall,
        rcpsp_improved=(rcpsp_wait < m_b.total_wait),
        ga_improved=(ga_wait < m_b.total_wait),
    )


# ---------------------------------------------------------------------------
# Print results table
# ---------------------------------------------------------------------------

_COL_W = 22

def _row(*cells, widths=None) -> str:
    widths = widths or [_COL_W] * len(cells)
    return "  ".join(str(c).ljust(w) for c, w in zip(cells, widths))


def print_table(results: List[ScenarioResult]) -> None:
    widths = [24, 7, 12, 12, 12, 10, 10, 8, 8]
    header = _row(
        "Scenario", "N", "Baseline Σw", "RCPSP Σw", "GA Σw",
        "RCPSP %", "GA %", "Rcpsp✓", "GA✓",
        widths=widths,
    )
    sep = "-" * len(header)
    print()
    print(sep)
    print(header)
    print(sep)
    for r in results:
        rcpsp_mark = "YES" if r.rcpsp_improved else "NO "
        ga_mark    = "YES" if r.ga_improved    else "NO "
        print(_row(
            r.label[:24],
            r.n_tasks,
            r.baseline_wait,
            r.rcpsp_wait,
            r.ga_wait,
            f"{r.rcpsp_pct:+.1f}%",
            f"{r.ga_pct:+.1f}%",
            rcpsp_mark,
            ga_mark,
            widths=widths,
        ))
    print(sep)


def print_verdict(results: List[ScenarioResult]) -> None:
    n_total    = len(results)
    rcpsp_pass = sum(1 for r in results if r.rcpsp_improved)
    ga_pass    = sum(1 for r in results if r.ga_improved)

    print()
    print("=== GENERALISATION VERDICT ===")
    print(f"  Scenarios run          : {n_total}")
    print(f"  RCPSP improved (strict): {rcpsp_pass}/{n_total}  "
          f"{'PASS — sign consistent' if rcpsp_pass == n_total else 'PARTIAL/FAIL — see table'}")
    print(f"  GA    improved         : {ga_pass}/{n_total}  "
          f"{'PASS — sign consistent' if ga_pass == n_total else 'PARTIAL — GA evaluated on speed/scalability axis'}")

    if rcpsp_pass == n_total:
        avg_rcpsp = sum(r.rcpsp_pct for r in results) / n_total
        print(f"  RCPSP avg improvement  : {avg_rcpsp:.1f}%")
        print("  Generalisation SUPPORTED: RCPSP Σwait reduction sign is "
              "consistent across all scenarios (Extension B acceptance criterion met).")
    else:
        failed = [r.label for r in results if not r.rcpsp_improved]
        print(f"  WARNING: RCPSP did not improve on: {failed}")
        print("  Possible causes: very tight time limit, trivial instance "
              "(baseline already near-optimal), or infeasible solve.")

    if ga_pass < n_total:
        failed_ga = [r.label for r in results if not r.ga_improved]
        print(f"  GA note: did not improve on {failed_ga}. "
              "GA acceptance axis is wall-clock scalability, not quality guarantee.")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 60)
    print("Extension B -- Generalisation Study")
    print(f"  Scenarios : {len(SCENARIOS)}")
    print(f"  RCPSP limit: {RCPSP_TIME_LIMIT}s  GA limit: {GA_TIME_LIMIT}s")
    print(f"  Mode: {'QUICK' if QUICK else 'FULL'}")
    print("=" * 60)

    results: List[ScenarioResult] = []
    total_t0 = time.perf_counter()

    for scenario in SCENARIOS:
        print(f"\nScenario: {scenario['label']}")
        r = run_scenario(scenario)
        results.append(r)
        print(f"  done: baseline={r.baseline_wait}, "
              f"rcpsp={r.rcpsp_wait} ({r.rcpsp_pct:+.1f}%), "
              f"ga={r.ga_wait} ({r.ga_pct:+.1f}%)")

    total_elapsed = time.perf_counter() - total_t0
    print(f"\nTotal wall-clock: {total_elapsed:.1f}s")

    print_table(results)
    print_verdict(results)

    # Return 0 if RCPSP passes all, 1 otherwise (useful for CI)
    rcpsp_all_pass = all(r.rcpsp_improved for r in results)
    return 0 if rcpsp_all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
