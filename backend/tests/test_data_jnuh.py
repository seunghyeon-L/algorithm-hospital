"""Tests for the JNUH surgical-department instance generator."""

import pytest

from backend.app.data import (
    _JNUH_OR_BLOCKS,
    _JNUH_SURGEONS,
    generate_jnuh_instance,
)
from backend.app.baseline import schedule_baseline


class TestJnuhStructure:
    def test_three_tasks_per_patient(self):
        inst = generate_jnuh_instance(n_patients=10, seed=42)
        assert len(inst.tasks) == 30
        for p in range(10):
            pid = f"P{p:03d}"
            assert f"{pid}_exam" in inst.tasks
            assert f"{pid}_surg" in inst.tasks
            assert f"{pid}_rec" in inst.tasks

    def test_chain_precedence(self):
        inst = generate_jnuh_instance(n_patients=5, seed=1)
        for p in range(5):
            pid = f"P{p:03d}"
            assert inst.tasks[f"{pid}_exam"].predecessors == []
            assert inst.tasks[f"{pid}_surg"].predecessors == [f"{pid}_exam"]
            assert inst.tasks[f"{pid}_rec"].predecessors == [f"{pid}_surg"]

    def test_surgery_resource_keys(self):
        inst = generate_jnuh_instance(n_patients=20, seed=42)
        for p in range(20):
            res = inst.tasks[f"P{p:03d}_surg"].resources
            assert res.get("room") == 1
            assert res.get("anesthesia") == 1
            assert 1 <= res.get("staff", 0) <= 3
            surg_keys = [k for k in res if k.startswith("surg_")]
            assert len(surg_keys) == 1
            assert surg_keys[0] in _JNUH_SURGEONS

    def test_exam_recovery_use_staff_only(self):
        inst = generate_jnuh_instance(n_patients=8, seed=7)
        for p in range(8):
            for suffix in ("_exam", "_rec"):
                res = inst.tasks[f"P{p:03d}{suffix}"].resources
                assert res == {"staff": 1}


class TestJnuhCapacities:
    def test_normal_capacities(self):
        inst = generate_jnuh_instance(n_patients=10, seed=42)
        caps = inst.resource_capacities
        assert caps["room"] == 12
        assert caps["anesthesia"] == 8
        assert caps["surg_gs"] == 11
        assert caps["surg_cs"] == 1
        assert caps["surg_ps"] == 1

    def test_crisis_room_reduction(self):
        inst = generate_jnuh_instance(n_patients=10, seed=42, crisis=True)
        assert inst.resource_capacities["room"] == 8
        assert "crisis" in inst.instance_id

    def test_pool_mode_has_no_orblocks(self):
        inst = generate_jnuh_instance(n_patients=10, seed=42)
        assert not any(k.startswith("orblock_") for k in inst.resource_capacities)

    def test_dedicated_blocks_sum_to_twelve(self):
        inst = generate_jnuh_instance(n_patients=10, seed=42, dedicated_blocks=True)
        blocks = {k: v for k, v in inst.resource_capacities.items()
                  if k.startswith("orblock_")}
        assert blocks == _JNUH_OR_BLOCKS
        assert sum(blocks.values()) == 12

    def test_dedicated_blocks_on_surgeries(self):
        inst = generate_jnuh_instance(n_patients=30, seed=3, dedicated_blocks=True)
        for tid, task in inst.tasks.items():
            if tid.endswith("_surg"):
                block_keys = [k for k in task.resources if k.startswith("orblock_")]
                assert len(block_keys) == 1
                # thoracic/plastic must share the general-surgery block
                if "surg_cs" in task.resources or "surg_ps" in task.resources:
                    assert block_keys[0] == "orblock_gs"

    def test_turnover_default(self):
        inst = generate_jnuh_instance(n_patients=5, seed=42)
        assert inst.turnover == 20


class TestJnuhDistributions:
    def test_reproducible(self):
        a = generate_jnuh_instance(n_patients=25, seed=99)
        b = generate_jnuh_instance(n_patients=25, seed=99)
        assert [t.duration for t in a.task_list()] == [t.duration for t in b.task_list()]
        assert [t.resources for t in a.task_list()] == [t.resources for t in b.task_list()]

    def test_different_seeds_differ(self):
        a = generate_jnuh_instance(n_patients=25, seed=1)
        b = generate_jnuh_instance(n_patients=25, seed=2)
        assert [t.duration for t in a.task_list()] != [t.duration for t in b.task_list()]

    def test_duration_bounds(self):
        inst = generate_jnuh_instance(n_patients=100, seed=42)
        for task in inst.task_list():
            assert 10 <= task.duration <= 420

    def test_scarce_departments_get_few_cases(self):
        inst = generate_jnuh_instance(n_patients=100, seed=42)
        scarce = sum(
            1 for t in inst.task_list()
            if "surg_cs" in t.resources or "surg_ps" in t.resources
        )
        # ~4% expected; allow generous margin but must stay a small minority
        assert scarce <= 15

    def test_n_patients_out_of_range(self):
        with pytest.raises(ValueError):
            generate_jnuh_instance(n_patients=0)
        with pytest.raises(ValueError):
            generate_jnuh_instance(n_patients=201)


class TestJnuhSchedulable:
    """The greedy baseline must handle the new resource keys unchanged."""

    def test_baseline_feasible_pool(self):
        inst = generate_jnuh_instance(n_patients=15, seed=42)
        sched = schedule_baseline(inst)
        sched.validate(inst)
        assert sched.total_wait(inst) >= 0

    def test_baseline_feasible_blocks_crisis(self):
        inst = generate_jnuh_instance(
            n_patients=15, seed=42, crisis=True, dedicated_blocks=True
        )
        sched = schedule_baseline(inst)
        sched.validate(inst)
