"""
tests/test_metrics.py — unit tests for metrics.py with hand-calculated examples.

Hand-calc small example (3 tasks, 1 room):
  Tasks:
    T1: duration=10, no predecessors, resources={'room':1}
    T2: duration=5,  predecessors=[T1], resources={'room':1}
    T3: duration=8,  predecessors=[T1], resources={'room':1}

  Baseline-like schedule (sequential, one room):
    T1: start=0,  end=10  → ready=0,  wait=0-0=0
    T2: start=10, end=15  → ready=10, wait=10-10=0
    T3: start=15, end=23  → ready=10, wait=15-10=5

  Σ wait = 0 + 0 + 5 = 5
  makespan = 23

  Schedule with wait (room contention forces T2 to wait):
    T1: start=0,  end=10  → ready=0,  wait=0
    T2: start=12, end=17  → ready=10, wait=12-10=2
    T3: start=17, end=25  → ready=10, wait=17-10=7

  Σ wait = 0 + 2 + 7 = 9
  makespan = 25

Resource utilisation example (single room, capacity=1):
  For the first schedule (makespan=23, capacity=1):
    busy_room = 1*10 + 1*5 + 1*8 = 23
    utilisation = 23 / (1 * 23) = 1.0

  For two rooms (capacity=2, same schedule):
    utilisation = 23 / (2 * 23) = 0.5

% improvement:
  baseline_wait=9, improved_wait=5 → (9-5)/9 * 100 = 44.44...%
"""

import pytest

from backend.app.model import Instance, Schedule, Task, TaskAssignment
from backend.app.metrics import evaluate, compare, ScheduleMetrics


# ---------------------------------------------------------------------------
# Shared fixture: 3-task instance
# ---------------------------------------------------------------------------

def make_3task_instance(num_rooms: int = 1) -> Instance:
    """3 tasks: T1 (root), T2 and T3 both depend on T1."""
    tasks = {
        "T1": Task(task_id="T1", duration=10, resources={"room": 1}, predecessors=[]),
        "T2": Task(task_id="T2", duration=5,  resources={"room": 1}, predecessors=["T1"]),
        "T3": Task(task_id="T3", duration=8,  resources={"room": 1}, predecessors=["T1"]),
    }
    return Instance(
        instance_id="test-3task",
        tasks=tasks,
        resource_capacities={"room": num_rooms},
        seed=0,
    )


def make_schedule_no_wait(instance: Instance) -> Schedule:
    """T1→T2→T3 sequential on one room. Σwait=5 (T3 waits 5 for room)."""
    return Schedule(
        instance_id=instance.instance_id,
        algo="test-no-wait",
        assignments={
            "T1": TaskAssignment(task_id="T1", start=0,  end=10, room="room-1"),
            "T2": TaskAssignment(task_id="T2", start=10, end=15, room="room-1"),
            "T3": TaskAssignment(task_id="T3", start=15, end=23, room="room-1"),
        },
        wall_clock_sec=0.001,
    )


def make_schedule_with_wait(instance: Instance) -> Schedule:
    """T1 at 0-10; T2 at 12-17 (waits 2); T3 at 17-25 (waits 7). Σwait=9."""
    return Schedule(
        instance_id=instance.instance_id,
        algo="test-with-wait",
        assignments={
            "T1": TaskAssignment(task_id="T1", start=0,  end=10, room="room-1"),
            "T2": TaskAssignment(task_id="T2", start=12, end=17, room="room-1"),
            "T3": TaskAssignment(task_id="T3", start=17, end=25, room="room-1"),
        },
        wall_clock_sec=0.002,
    )


# ---------------------------------------------------------------------------
# Tests: total_wait (PINNED headline)
# ---------------------------------------------------------------------------

class TestTotalWait:
    def test_no_wait_schedule(self):
        """Hand-calc: T1 wait=0, T2 wait=0, T3 wait=5 → Σwait=5."""
        inst = make_3task_instance()
        sched = make_schedule_no_wait(inst)
        m = evaluate(sched, inst)
        assert m.total_wait == 5

    def test_with_wait_schedule(self):
        """Hand-calc: T1 wait=0, T2 wait=2, T3 wait=7 → Σwait=9."""
        inst = make_3task_instance()
        sched = make_schedule_with_wait(inst)
        m = evaluate(sched, inst)
        assert m.total_wait == 9

    def test_zero_wait_all_parallel(self):
        """3 independent tasks starting at 0 in separate rooms → Σwait=0."""
        tasks = {
            "A": Task(task_id="A", duration=5, resources={"room": 1}, predecessors=[]),
            "B": Task(task_id="B", duration=3, resources={"room": 1}, predecessors=[]),
            "C": Task(task_id="C", duration=7, resources={"room": 1}, predecessors=[]),
        }
        inst = Instance(
            instance_id="parallel",
            tasks=tasks,
            resource_capacities={"room": 3},
        )
        sched = Schedule(
            instance_id="parallel",
            algo="test",
            assignments={
                "A": TaskAssignment(task_id="A", start=0, end=5,  room="room-1"),
                "B": TaskAssignment(task_id="B", start=0, end=3,  room="room-2"),
                "C": TaskAssignment(task_id="C", start=0, end=7,  room="room-3"),
            },
        )
        m = evaluate(sched, inst)
        assert m.total_wait == 0


# ---------------------------------------------------------------------------
# Tests: makespan
# ---------------------------------------------------------------------------

class TestMakespan:
    def test_makespan_no_wait(self):
        """Last task ends at 23."""
        inst = make_3task_instance()
        sched = make_schedule_no_wait(inst)
        m = evaluate(sched, inst)
        assert m.makespan == 23

    def test_makespan_with_wait(self):
        """Last task ends at 25."""
        inst = make_3task_instance()
        sched = make_schedule_with_wait(inst)
        m = evaluate(sched, inst)
        assert m.makespan == 25


# ---------------------------------------------------------------------------
# Tests: resource utilisation
# ---------------------------------------------------------------------------

class TestResourceUtilisation:
    def test_full_utilisation_1_room(self):
        """1 room, tasks fill all time slots → utilisation=1.0."""
        inst = make_3task_instance(num_rooms=1)
        sched = make_schedule_no_wait(inst)
        m = evaluate(sched, inst)
        # busy = 10+5+8=23, capacity*makespan = 1*23 = 23 → 1.0
        assert abs(m.resource_utilization["room"] - 1.0) < 1e-9

    def test_half_utilisation_2_rooms(self):
        """2 rooms but tasks still run sequentially → utilisation=0.5."""
        inst = make_3task_instance(num_rooms=2)
        sched = make_schedule_no_wait(inst)
        m = evaluate(sched, inst)
        # busy = 23, capacity*makespan = 2*23 = 46 → 0.5
        assert abs(m.resource_utilization["room"] - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# Tests: wall_clock_sec passthrough
# ---------------------------------------------------------------------------

class TestWallClock:
    def test_wall_clock_stored(self):
        inst = make_3task_instance()
        sched = make_schedule_no_wait(inst)
        sched.wall_clock_sec = 1.234
        m = evaluate(sched, inst)
        assert abs(m.wall_clock_sec - 1.234) < 1e-9


# ---------------------------------------------------------------------------
# Tests: % improvement vs baseline
# ---------------------------------------------------------------------------

class TestPctImprovement:
    def test_improvement_over_baseline(self):
        """baseline_wait=9, improved=5 → (9-5)/9*100 ≈ 44.44%."""
        inst = make_3task_instance()
        improved = make_schedule_no_wait(inst)
        m = evaluate(improved, inst, baseline_wait=9)
        expected = 100.0 * (9 - 5) / 9
        assert abs(m.pct_improvement_vs_baseline - expected) < 1e-6

    def test_no_improvement(self):
        """Same schedule as baseline → 0% improvement."""
        inst = make_3task_instance()
        sched = make_schedule_with_wait(inst)
        m = evaluate(sched, inst, baseline_wait=9)
        assert abs(m.pct_improvement_vs_baseline - 0.0) < 1e-9

    def test_baseline_wait_zero(self):
        """baseline_wait=0 → pct_improvement=0.0 (not division by zero)."""
        inst = make_3task_instance()
        sched = make_schedule_no_wait(inst)
        m = evaluate(sched, inst, baseline_wait=0)
        assert m.pct_improvement_vs_baseline == 0.0

    def test_no_baseline_provided(self):
        """Without baseline_wait, pct_improvement_vs_baseline is None."""
        inst = make_3task_instance()
        sched = make_schedule_no_wait(inst)
        m = evaluate(sched, inst)
        assert m.pct_improvement_vs_baseline is None


# ---------------------------------------------------------------------------
# Tests: task breakdown
# ---------------------------------------------------------------------------

class TestTaskBreakdown:
    def test_breakdown_included(self):
        inst = make_3task_instance()
        sched = make_schedule_no_wait(inst)
        m = evaluate(sched, inst, include_task_breakdown=True)
        assert m.task_breakdown is not None
        assert set(m.task_breakdown.keys()) == {"T1", "T2", "T3"}
        assert m.task_breakdown["T1"].wait == 0
        assert m.task_breakdown["T1"].ready == 0
        assert m.task_breakdown["T2"].ready == 10
        assert m.task_breakdown["T2"].wait == 0
        assert m.task_breakdown["T3"].ready == 10
        assert m.task_breakdown["T3"].wait == 5

    def test_breakdown_excluded_by_default(self):
        inst = make_3task_instance()
        sched = make_schedule_no_wait(inst)
        m = evaluate(sched, inst)
        assert m.task_breakdown is None


# ---------------------------------------------------------------------------
# Tests: compare() helper
# ---------------------------------------------------------------------------

class TestCompare:
    def test_compare_two_schedules(self):
        inst = make_3task_instance()
        baseline = make_schedule_with_wait(inst)
        baseline.algo = "baseline"
        improved = make_schedule_no_wait(inst)
        improved.algo = "rcpsp"

        results = compare(
            {"baseline": baseline, "rcpsp": improved},
            inst,
            baseline_algo="baseline",
        )

        assert set(results.keys()) == {"baseline", "rcpsp"}
        assert results["baseline"].total_wait == 9
        assert results["rcpsp"].total_wait == 5
        # baseline gets pct_improvement=0.0
        assert results["baseline"].pct_improvement_vs_baseline == 0.0
        # rcpsp improves by (9-5)/9*100
        expected = 100.0 * (9 - 5) / 9
        assert abs(results["rcpsp"].pct_improvement_vs_baseline - expected) < 1e-6

    def test_compare_missing_baseline(self):
        """If baseline_algo not in schedules, pct_improvement stays None."""
        inst = make_3task_instance()
        sched = make_schedule_no_wait(inst)
        sched.algo = "rcpsp"
        results = compare({"rcpsp": sched}, inst, baseline_algo="baseline")
        assert results["rcpsp"].pct_improvement_vs_baseline is None


# ---------------------------------------------------------------------------
# Tests: as_dict serialisation
# ---------------------------------------------------------------------------

class TestAsDict:
    def test_as_dict_keys(self):
        inst = make_3task_instance()
        sched = make_schedule_no_wait(inst)
        m = evaluate(sched, inst)
        d = m.as_dict()
        for key in ("instance_id", "algo", "total_wait", "makespan",
                    "resource_utilization", "wall_clock_sec", "n_tasks",
                    "pct_improvement_vs_baseline"):
            assert key in d

    def test_as_dict_values(self):
        inst = make_3task_instance()
        sched = make_schedule_no_wait(inst)
        m = evaluate(sched, inst)
        d = m.as_dict()
        assert d["total_wait"] == 5
        assert d["makespan"] == 23
        assert d["n_tasks"] == 3
