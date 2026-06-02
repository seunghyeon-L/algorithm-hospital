"""
tests/test_model.py — smoke tests for shared data contract (model.py).

Verifies:
- Task / Instance / Schedule / TaskAssignment can be constructed.
- Instance.validate() catches bad inputs.
- Schedule.validate() enforces precedence and duration constraints.
- PINNED objective: ready(), wait(), total_wait(), makespan() match hand calc.
"""

import pytest
from backend.app.model import Instance, Schedule, Task, TaskAssignment


# ---------------------------------------------------------------------------
# Helpers: build a tiny 3-task chain  T1 -> T2 -> T3
# ---------------------------------------------------------------------------

def make_chain_instance() -> Instance:
    """T1(dur=5) -> T2(dur=3) -> T3(dur=7). One room, capacity=1."""
    tasks = {
        "T1": Task("T1", 5, {"room": 1}, predecessors=[]),
        "T2": Task("T2", 3, {"room": 1}, predecessors=["T1"]),
        "T3": Task("T3", 7, {"room": 1}, predecessors=["T2"]),
    }
    return Instance(
        instance_id="test-chain",
        tasks=tasks,
        resource_capacities={"room": 1},
        seed=0,
    )


def make_chain_schedule(instance: Instance, algo: str = "baseline") -> Schedule:
    """Sequential schedule: T1[0,5], T2[5,8], T3[8,15]. No wait."""
    return Schedule(
        instance_id=instance.instance_id,
        algo=algo,
        assignments={
            "T1": TaskAssignment("T1", start=0, end=5),
            "T2": TaskAssignment("T2", start=5, end=8),
            "T3": TaskAssignment("T3", start=8, end=15),
        },
    )


# ---------------------------------------------------------------------------
# Instance construction and validation
# ---------------------------------------------------------------------------

class TestInstance:
    def test_construct(self):
        inst = make_chain_instance()
        assert len(inst.tasks) == 3
        assert inst.resource_capacities["room"] == 1

    def test_edges(self):
        inst = make_chain_instance()
        edges = set(inst.edges())
        assert ("T1", "T2") in edges
        assert ("T2", "T3") in edges
        assert len(edges) == 2

    def test_validate_ok(self):
        make_chain_instance().validate()  # must not raise

    def test_validate_bad_duration(self):
        inst = make_chain_instance()
        inst.tasks["T1"].duration = 0
        with pytest.raises(ValueError, match="duration must be positive"):
            inst.validate()

    def test_validate_unknown_predecessor(self):
        inst = make_chain_instance()
        inst.tasks["T1"].predecessors = ["GHOST"]
        with pytest.raises(ValueError, match="unknown predecessor"):
            inst.validate()

    def test_validate_unknown_resource(self):
        inst = make_chain_instance()
        inst.tasks["T1"].resources = {"icu": 1}  # not in capacities
        with pytest.raises(ValueError, match="not in capacities"):
            inst.validate()


# ---------------------------------------------------------------------------
# Schedule validation
# ---------------------------------------------------------------------------

class TestScheduleValidate:
    def test_valid_chain(self):
        inst = make_chain_instance()
        sched = make_chain_schedule(inst)
        sched.validate(inst)  # must not raise

    def test_missing_task(self):
        inst = make_chain_instance()
        sched = make_chain_schedule(inst)
        del sched.assignments["T2"]
        with pytest.raises(ValueError, match="missing assignment"):
            sched.validate(inst)

    def test_wrong_end(self):
        inst = make_chain_instance()
        sched = make_chain_schedule(inst)
        sched.assignments["T1"].end = 99  # duration=5, so end should be 5
        with pytest.raises(ValueError, match="end=99"):
            sched.validate(inst)

    def test_negative_start(self):
        inst = make_chain_instance()
        sched = make_chain_schedule(inst)
        sched.assignments["T1"].start = -1
        sched.assignments["T1"].end = 4
        with pytest.raises(ValueError, match="negative"):
            sched.validate(inst)

    def test_precedence_violated(self):
        inst = make_chain_instance()
        sched = make_chain_schedule(inst)
        # T2 starts before T1 finishes
        sched.assignments["T2"].start = 3
        sched.assignments["T2"].end = 6
        with pytest.raises(ValueError, match="Precedence violated"):
            sched.validate(inst)


# ---------------------------------------------------------------------------
# PINNED objective: ready / wait / total_wait / makespan
# Hand-calc for chain [0,5], [5,8], [8,15] — no resource contention
# ready(T1)=0, ready(T2)=5, ready(T3)=8
# wait(T1)=0,  wait(T2)=0,  wait(T3)=0  => total_wait=0
# ---------------------------------------------------------------------------

class TestPinnedObjective:
    def test_ready_no_predecessors(self):
        inst = make_chain_instance()
        sched = make_chain_schedule(inst)
        assert sched.assignments["T1"].ready(inst, sched) == 0

    def test_ready_with_predecessor(self):
        inst = make_chain_instance()
        sched = make_chain_schedule(inst)
        # T2's predecessor T1 ends at 5
        assert sched.assignments["T2"].ready(inst, sched) == 5

    def test_wait_zero_for_tight_chain(self):
        inst = make_chain_instance()
        sched = make_chain_schedule(inst)
        for asgn in sched.assignments.values():
            assert asgn.wait(inst, sched) == 0

    def test_total_wait_zero(self):
        inst = make_chain_instance()
        sched = make_chain_schedule(inst)
        assert sched.total_wait(inst) == 0

    def test_total_wait_with_gap(self):
        """T2 starts at 7 instead of 5 (gap=2). total_wait should be 2."""
        inst = make_chain_instance()
        sched = Schedule(
            instance_id=inst.instance_id,
            algo="test",
            assignments={
                "T1": TaskAssignment("T1", 0, 5),
                "T2": TaskAssignment("T2", 7, 10),   # wait=2 (ready=5, start=7)
                "T3": TaskAssignment("T3", 10, 17),  # wait=0 (ready=10, start=10)
            },
        )
        assert sched.assignments["T2"].wait(inst, sched) == 2
        assert sched.assignments["T3"].wait(inst, sched) == 0
        assert sched.total_wait(inst) == 2

    def test_makespan(self):
        inst = make_chain_instance()
        sched = make_chain_schedule(inst)
        assert sched.makespan() == 15

    def test_summary_keys(self):
        inst = make_chain_instance()
        sched = make_chain_schedule(inst)
        s = sched.summary(inst)
        for key in ("instance_id", "algo", "total_wait", "makespan",
                    "wall_clock_sec", "n_tasks"):
            assert key in s

    def test_multiple_predecessors_ready(self):
        """T3 has two predecessors T1(end=5) and T2(end=8). ready=max=8."""
        tasks = {
            "T1": Task("T1", 5, {"room": 1}, predecessors=[]),
            "T2": Task("T2", 8, {"room": 1}, predecessors=[]),
            "T3": Task("T3", 4, {"room": 1}, predecessors=["T1", "T2"]),
        }
        inst = Instance("test-fork", tasks, {"room": 1})
        sched = Schedule(
            instance_id="test-fork",
            algo="test",
            assignments={
                "T1": TaskAssignment("T1", 0, 5),
                "T2": TaskAssignment("T2", 0, 8),
                "T3": TaskAssignment("T3", 8, 12),  # wait=0, ready=8
            },
        )
        assert sched.assignments["T3"].ready(inst, sched) == 8
        assert sched.assignments["T3"].wait(inst, sched) == 0
        assert sched.total_wait(inst) == 0
