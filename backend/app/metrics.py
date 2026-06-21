"""
metrics.py — single source of truth for all schedule evaluation metrics.

PINNED objective (identical to model.py docstring, enforced here):
  ready(task) = max finish of all predecessors (precedence-only, no resource).
                0 if no predecessors.
  wait(task)  = start(task) - ready(task)   [resource-contention delay]
  headline    = Σ_over_tasks wait(task)      [task-level total wait]

All algorithms (baseline, rcpsp, ga) optimise *this exact formula*.
metrics.py is the referee — it re-computes from Schedule + Instance directly,
never trusting algorithm-internal values.

Wall-clock timing helper: use `timer()` as a context manager.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Generator, Optional

from backend.app.model import Instance, Schedule


# ---------------------------------------------------------------------------
# Wall-clock timer helper
# ---------------------------------------------------------------------------

@contextmanager
def timer() -> Generator[None, None, None]:
    """Context manager that prints nothing; caller reads elapsed via the
    Schedule.wall_clock_sec field set *after* the with-block.

    Usage::

        t0 = time.perf_counter()
        with some_algo() as sched:
            pass
        sched.wall_clock_sec = time.perf_counter() - t0

    Or use the standalone `measure_wall_clock` helper below.
    """
    yield


def measure_wall_clock(fn, *args, **kwargs):
    """Call fn(*args, **kwargs), return (result, elapsed_seconds)."""
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - t0
    return result, elapsed


# ---------------------------------------------------------------------------
# Per-task breakdown
# ---------------------------------------------------------------------------

@dataclass
class TaskMetrics:
    """Metrics for a single task assignment."""

    task_id: str
    ready: int
    """max finish of predecessors (precedence-only). 0 if no predecessors."""

    start: int
    end: int
    wait: int
    """start - ready  (resource-contention delay >= 0)."""

    duration: int
    room: Optional[str]


# ---------------------------------------------------------------------------
# Schedule-level metrics
# ---------------------------------------------------------------------------

@dataclass
class ScheduleMetrics:
    """All metrics for one schedule — the referee output."""

    instance_id: str
    algo: str

    # --- PINNED headline ---
    total_wait: int
    """Σ wait(task) over all tasks. Task-level. Minimised by rcpsp/ga."""

    # --- auxiliary ---
    makespan: int
    """Latest end time across all task assignments."""

    resource_utilization: Dict[str, float]
    """Per resource type: sum(demand*duration) / (capacity * makespan).
    Value in [0, 1]; higher means busier."""

    wall_clock_sec: float
    """Wall-clock seconds the algorithm took (from Schedule.wall_clock_sec)."""

    n_tasks: int

    # --- optional baseline comparison ---
    pct_improvement_vs_baseline: Optional[float] = None
    """100 * (baseline_wait - this_wait) / baseline_wait.
    Positive = improvement over baseline. None if baseline not provided."""

    # --- per-task breakdown (for debugging / visualisation) ---
    task_breakdown: Dict[str, TaskMetrics] = None  # type: ignore[assignment]

    def as_dict(self) -> dict:
        """Plain dict suitable for JSON serialisation."""
        d = {
            "instance_id": self.instance_id,
            "algo": self.algo,
            "total_wait": self.total_wait,
            "makespan": self.makespan,
            "resource_utilization": self.resource_utilization,
            "wall_clock_sec": self.wall_clock_sec,
            "n_tasks": self.n_tasks,
            "pct_improvement_vs_baseline": self.pct_improvement_vs_baseline,
        }
        if self.task_breakdown:
            d["task_breakdown"] = {
                tid: {
                    "ready": tm.ready,
                    "start": tm.start,
                    "end": tm.end,
                    "wait": tm.wait,
                    "duration": tm.duration,
                    "room": tm.room,
                }
                for tid, tm in self.task_breakdown.items()
            }
        return d


# ---------------------------------------------------------------------------
# Core evaluation function
# ---------------------------------------------------------------------------

def evaluate(
    schedule: Schedule,
    instance: Instance,
    baseline_wait: Optional[int] = None,
    include_task_breakdown: bool = False,
) -> ScheduleMetrics:
    """Compute all metrics for *schedule* against *instance*.

    Parameters
    ----------
    schedule:
        Algorithm output — must cover all tasks in instance.
    instance:
        The scheduling problem instance.
    baseline_wait:
        If provided, compute pct_improvement_vs_baseline.
    include_task_breakdown:
        If True, populate task_breakdown in the result.

    Returns
    -------
    ScheduleMetrics
        All computed metrics. total_wait is the PINNED headline.
    """
    # Validate schedule shape first
    schedule.validate(instance)

    # --- per-task metrics ---
    task_metrics: Dict[str, TaskMetrics] = {}
    total_wait = 0

    for task_id, asgn in schedule.assignments.items():
        task = instance.tasks[task_id]

        # ready = max(release_time, max predecessor finish) — precedence-only
        ready_time = task.release_time
        if task.predecessors:
            ready_time = max(
                ready_time,
                max(
                    schedule.assignments[pred_id].end
                    for pred_id in task.predecessors
                ),
            )

        wait_time = asgn.start - ready_time
        total_wait += wait_time

        task_metrics[task_id] = TaskMetrics(
            task_id=task_id,
            ready=ready_time,
            start=asgn.start,
            end=asgn.end,
            wait=wait_time,
            duration=task.duration,
            room=asgn.room,
        )

    # --- makespan ---
    makespan = max(asgn.end for asgn in schedule.assignments.values())

    # --- resource utilisation ---
    resource_utilization: Dict[str, float] = {}
    if makespan > 0:
        for res, capacity in instance.resource_capacities.items():
            busy_time = sum(
                instance.tasks[task_id].resources.get(res, 0) * tm.duration
                for task_id, tm in task_metrics.items()
            )
            denominator = capacity * makespan
            resource_utilization[res] = busy_time / denominator if denominator > 0 else 0.0
    else:
        resource_utilization = {res: 0.0 for res in instance.resource_capacities}

    # --- % improvement vs baseline ---
    pct_improvement: Optional[float] = None
    if baseline_wait is not None:
        if baseline_wait > 0:
            pct_improvement = 100.0 * (baseline_wait - total_wait) / baseline_wait
        elif baseline_wait == 0:
            # baseline already optimal; improvement is 0 % (or undefined)
            pct_improvement = 0.0

    return ScheduleMetrics(
        instance_id=schedule.instance_id,
        algo=schedule.algo,
        total_wait=total_wait,
        makespan=makespan,
        resource_utilization=resource_utilization,
        wall_clock_sec=schedule.wall_clock_sec,
        n_tasks=len(schedule.assignments),
        pct_improvement_vs_baseline=pct_improvement,
        task_breakdown=task_metrics if include_task_breakdown else None,
    )


# ---------------------------------------------------------------------------
# Convenience: compare multiple schedules
# ---------------------------------------------------------------------------

def compare(
    schedules: Dict[str, Schedule],
    instance: Instance,
    baseline_algo: str = "baseline",
    include_task_breakdown: bool = False,
) -> Dict[str, ScheduleMetrics]:
    """Evaluate all schedules and cross-compare against the baseline.

    Parameters
    ----------
    schedules:
        Mapping algo_name -> Schedule.
    instance:
        Shared problem instance.
    baseline_algo:
        Key in *schedules* to use as the reference for %improvement.
    include_task_breakdown:
        Passed through to evaluate().

    Returns
    -------
    Dict[str, ScheduleMetrics]
        Mapping algo_name -> ScheduleMetrics, with pct_improvement populated
        for all non-baseline algorithms.
    """
    baseline_wait: Optional[int] = None
    if baseline_algo in schedules:
        # Evaluate baseline first to get its total_wait
        baseline_metrics = evaluate(
            schedules[baseline_algo],
            instance,
            baseline_wait=None,
            include_task_breakdown=include_task_breakdown,
        )
        baseline_wait = baseline_metrics.total_wait

    results: Dict[str, ScheduleMetrics] = {}
    for algo, sched in schedules.items():
        if algo == baseline_algo and baseline_wait is not None:
            # Reuse already-computed metrics, just attach pct_improvement = 0
            m = baseline_metrics  # type: ignore[possibly-undefined]
            results[algo] = ScheduleMetrics(
                instance_id=m.instance_id,
                algo=m.algo,
                total_wait=m.total_wait,
                makespan=m.makespan,
                resource_utilization=m.resource_utilization,
                wall_clock_sec=m.wall_clock_sec,
                n_tasks=m.n_tasks,
                pct_improvement_vs_baseline=0.0,
                task_breakdown=m.task_breakdown,
            )
        else:
            results[algo] = evaluate(
                sched,
                instance,
                baseline_wait=baseline_wait,
                include_task_breakdown=include_task_breakdown,
            )

    return results
