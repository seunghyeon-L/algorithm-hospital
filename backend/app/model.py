"""
model.py — shared data contract for all algorithms.

PINNED objective (from plan):
  ready(task) = max finish time of all predecessors (precedence-only, no resource).
                0 if no predecessors.
  wait(task)  = start(task) - ready(task)   [resource-contention delay]
  headline    = Σ_over_tasks wait(task)      [task-level total wait]

All algorithms (baseline, rcpsp, ga) MUST produce a Schedule of this shape.
metrics.py consumes only Schedule + Instance — nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Task node
# ---------------------------------------------------------------------------

@dataclass
class Task:
    """A single schedulable unit (surgery, exam, prep, etc.)."""

    task_id: str
    """Unique identifier within an Instance (e.g. 'T01', 'T02')."""

    duration: int
    """Duration in minutes (positive integer)."""

    resources: Dict[str, int]
    """Resource demands: {'room': 1, 'staff': 2, ...}.
    Keys must match Instance.resource_capacities."""

    predecessors: List[str] = field(default_factory=list)
    """task_ids that must finish before this task can start."""

    label: Optional[str] = None
    """Human-readable name (e.g. 'Appendectomy prep')."""

    patient_id: Optional[str] = None
    """Optional grouping key for patient-level reporting."""

    release_time: int = 0
    """Earliest permissible start (patient arrival / emergency release time).
    0 = available from t=0 (default, backward-compatible).  ready(task) is
    raised to at least release_time, so a task cannot start before it."""


# ---------------------------------------------------------------------------
# Instance (problem input)
# ---------------------------------------------------------------------------

@dataclass
class Instance:
    """A complete scheduling problem instance.

    Contains tasks, precedence edges (derived from Task.predecessors),
    resource capacities, and metadata for reproducibility.
    """

    instance_id: str
    """Unique name, e.g. 'synth-seed42-n30' or 'psplib-j30-1'."""

    tasks: Dict[str, Task]
    """Mapping task_id -> Task. Defines the node set."""

    resource_capacities: Dict[str, int]
    """Available capacity per resource type, e.g. {'room': 3, 'staff': 5}."""

    seed: Optional[int] = None
    """RNG seed used to generate this instance (None for real/PSPLIB data)."""

    source: str = "synthetic"
    """Origin: 'synthetic' | 'psplib' | 'manual'."""

    turnover: int = 0
    """수술실 전환시간(분): 같은 방 연속 케이스 사이 청소·준비 시간.
    대기시간 정의(Σwait)에는 영향이 없고 방 가용성에만 영향을 준다(현장 KPI: 중앙값 ~28.5분)."""

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    def task_list(self) -> List[Task]:
        """Return tasks in insertion order (not topologically sorted)."""
        return list(self.tasks.values())

    def edges(self) -> List[Tuple[str, str]]:
        """Return all (predecessor_id, successor_id) edges."""
        result: List[Tuple[str, str]] = []
        for task in self.tasks.values():
            for pred in task.predecessors:
                result.append((pred, task.task_id))
        return result

    def validate(self) -> None:
        """Raise ValueError if instance is structurally invalid."""
        for task in self.tasks.values():
            if task.duration <= 0:
                raise ValueError(
                    f"Task {task.task_id}: duration must be positive, got {task.duration}"
                )
            for pred in task.predecessors:
                if pred not in self.tasks:
                    raise ValueError(
                        f"Task {task.task_id}: unknown predecessor '{pred}'"
                    )
            for res, demand in task.resources.items():
                if res not in self.resource_capacities:
                    raise ValueError(
                        f"Task {task.task_id}: resource '{res}' not in capacities"
                    )
                if demand < 0:
                    raise ValueError(
                        f"Task {task.task_id}: resource demand must be non-negative"
                    )


# ---------------------------------------------------------------------------
# TaskAssignment (one row of a Schedule)
# ---------------------------------------------------------------------------

@dataclass
class TaskAssignment:
    """Placement of a single task in the schedule."""

    task_id: str
    start: int
    """Start time in minutes."""

    end: int
    """End time in minutes. Must equal start + task.duration."""

    room: Optional[str] = None
    """Which room/resource slot was assigned (optional label)."""

    # ------------------------------------------------------------------
    # PINNED objective helpers
    # ------------------------------------------------------------------

    def ready(self, instance: Instance, schedule: "Schedule") -> int:
        """ready(task) = max(release_time, max finish of predecessors).
        With no predecessors this is just release_time (0 by default)."""
        task = instance.tasks[self.task_id]
        base = task.release_time
        if not task.predecessors:
            return base
        return max(
            base,
            max(schedule.assignments[pred].end for pred in task.predecessors),
        )

    def wait(self, instance: Instance, schedule: "Schedule") -> int:
        """wait(task) = start - ready(task).  Non-negative by construction."""
        return self.start - self.ready(instance, schedule)


# ---------------------------------------------------------------------------
# Schedule (algorithm output)
# ---------------------------------------------------------------------------

@dataclass
class Schedule:
    """Complete schedule produced by any algorithm.

    Shape contract (enforced by validate()):
      - Every task in Instance has exactly one TaskAssignment.
      - end == start + duration for every assignment.
      - start >= 0.
    """

    instance_id: str
    algo: str
    """Algorithm that produced this schedule: 'baseline' | 'rcpsp' | 'ga'."""

    assignments: Dict[str, TaskAssignment]
    """task_id -> TaskAssignment."""

    wall_clock_sec: float = 0.0
    """Wall-clock seconds the algorithm took to produce this schedule."""

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, instance: Instance) -> None:
        """Raise ValueError if schedule is inconsistent with instance."""
        # All tasks covered
        for task_id in instance.tasks:
            if task_id not in self.assignments:
                raise ValueError(f"Schedule missing assignment for task {task_id}")

        for task_id, asgn in self.assignments.items():
            if task_id not in instance.tasks:
                raise ValueError(f"Schedule has unknown task_id {task_id}")
            task = instance.tasks[task_id]

            if asgn.start < 0:
                raise ValueError(f"Task {task_id}: start={asgn.start} is negative")

            if asgn.start < task.release_time:
                raise ValueError(
                    f"Task {task_id}: start={asgn.start} < release_time={task.release_time}"
                )

            expected_end = asgn.start + task.duration
            if asgn.end != expected_end:
                raise ValueError(
                    f"Task {task_id}: end={asgn.end} != start+duration={expected_end}"
                )

            # Precedence: every predecessor must finish <= this task's start
            for pred_id in task.predecessors:
                pred_end = self.assignments[pred_id].end
                if pred_end > asgn.start:
                    raise ValueError(
                        f"Precedence violated: {pred_id} ends at {pred_end} "
                        f"but {task_id} starts at {asgn.start}"
                    )

    # ------------------------------------------------------------------
    # PINNED objective computation
    # ------------------------------------------------------------------

    def total_wait(self, instance: Instance) -> int:
        """Σ wait(task) — headline metric (PINNED, task-level)."""
        return sum(
            asgn.wait(instance, self) for asgn in self.assignments.values()
        )

    def makespan(self) -> int:
        """Latest end time across all assignments."""
        return max(asgn.end for asgn in self.assignments.values())

    def summary(self, instance: Instance) -> Dict[str, object]:
        """Return a plain dict with key metrics for JSON serialisation."""
        return {
            "instance_id": self.instance_id,
            "algo": self.algo,
            "total_wait": self.total_wait(instance),
            "makespan": self.makespan(),
            "wall_clock_sec": self.wall_clock_sec,
            "n_tasks": len(self.assignments),
        }
