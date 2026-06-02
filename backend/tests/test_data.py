"""
tests/test_data.py — tests for data.py synthetic generator + PSPLIB parser.

Verifies:
- Seed reproducibility: same seed -> same instance (task ids, durations, predecessors).
- Different seeds -> different instances.
- Instance passes validate().
- n_tasks respected (30, 40, 50).
- Resource capacities set correctly.
- PSPLIB parser raises FileNotFoundError on missing file.
- PSPLIB parser raises ValueError on malformed content.
"""

import os
import tempfile
import pytest
from backend.app.data import generate_instance, parse_psplib
from backend.app.model import Instance


# ---------------------------------------------------------------------------
# Synthetic generator tests
# ---------------------------------------------------------------------------

class TestGenerateInstance:
    def test_seed_reproducibility(self):
        """Same seed must produce byte-identical instance."""
        inst_a = generate_instance(n_tasks=30, seed=42)
        inst_b = generate_instance(n_tasks=30, seed=42)
        assert inst_a.instance_id == inst_b.instance_id
        assert list(inst_a.tasks.keys()) == list(inst_b.tasks.keys())
        for tid in inst_a.tasks:
            ta = inst_a.tasks[tid]
            tb = inst_b.tasks[tid]
            assert ta.duration == tb.duration
            assert ta.resources == tb.resources
            assert ta.predecessors == tb.predecessors

    def test_different_seeds_differ(self):
        """Different seeds should produce different durations (with high probability)."""
        inst_a = generate_instance(n_tasks=30, seed=1)
        inst_b = generate_instance(n_tasks=30, seed=2)
        durations_a = [t.duration for t in inst_a.tasks.values()]
        durations_b = [t.duration for t in inst_b.tasks.values()]
        assert durations_a != durations_b

    def test_n_tasks_30(self):
        inst = generate_instance(n_tasks=30, seed=0)
        assert len(inst.tasks) == 30

    def test_n_tasks_40(self):
        inst = generate_instance(n_tasks=40, seed=0)
        assert len(inst.tasks) == 40

    def test_n_tasks_50(self):
        inst = generate_instance(n_tasks=50, seed=0)
        assert len(inst.tasks) == 50

    def test_instance_id_contains_seed_and_n(self):
        inst = generate_instance(n_tasks=35, seed=99)
        assert "seed99" in inst.instance_id
        assert "n35" in inst.instance_id

    def test_resource_capacities(self):
        inst = generate_instance(n_tasks=30, seed=42, n_rooms=3, n_staff=5)
        assert inst.resource_capacities["room"] == 3
        assert inst.resource_capacities["staff"] == 5

    def test_validate_passes(self):
        """generate_instance must return a structurally valid Instance."""
        inst = generate_instance(n_tasks=35, seed=7)
        inst.validate()  # must not raise

    def test_is_dag(self):
        """Generated instance must be acyclic (edges only go i->j where i<j)."""
        from backend.app.graph import is_dag
        inst = generate_instance(n_tasks=30, seed=42)
        assert is_dag(inst)

    def test_durations_in_range(self):
        inst = generate_instance(n_tasks=30, seed=42, min_duration=5, max_duration=120)
        for task in inst.tasks.values():
            assert 5 <= task.duration <= 120

    def test_predecessors_only_earlier_tasks(self):
        """No task should list a same-index or later task as predecessor."""
        inst = generate_instance(n_tasks=30, seed=42)
        task_ids = list(inst.tasks.keys())
        for i, tid in enumerate(task_ids):
            for pred in inst.tasks[tid].predecessors:
                pred_idx = task_ids.index(pred)
                assert pred_idx < i, f"{tid} lists {pred} (idx {pred_idx}) as predecessor"

    def test_source_field(self):
        inst = generate_instance(n_tasks=30, seed=0)
        assert inst.source == "synthetic"

    def test_seed_stored(self):
        inst = generate_instance(n_tasks=30, seed=123)
        assert inst.seed == 123

    def test_room_demand_is_one(self):
        """Each task should demand exactly 1 room."""
        inst = generate_instance(n_tasks=30, seed=42)
        for task in inst.tasks.values():
            assert task.resources["room"] == 1

    def test_invalid_n_tasks(self):
        with pytest.raises(ValueError):
            generate_instance(n_tasks=0, seed=0)


# ---------------------------------------------------------------------------
# PSPLIB parser tests
# ---------------------------------------------------------------------------

class TestParsePsplib:
    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            parse_psplib("/nonexistent/path/to/file.sm")

    def test_malformed_file_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".sm", mode="w",
                                         delete=False, encoding="utf-8") as f:
            f.write("This is not a valid PSPLIB file.\n")
            tmp_path = f.name
        try:
            with pytest.raises(ValueError):
                parse_psplib(tmp_path)
        finally:
            os.unlink(tmp_path)

    def test_minimal_psplib(self):
        """Parse a hand-crafted minimal .sm file with 3 jobs."""
        content = """\
************************************************************************
file with basedata            : generated
initial value random generator: 12345
************************************************************************
projects                      :  1
jobs (incl. supersource/sink ): 3
horizon                       :  50
RESOURCES
  - renewable                 :  2   R
  - nonrenewable              :  0   N
  - doubly constrained        :  0   D
************************************************************************
PROJECT INFORMATION:
pronr.  #jobs rel.date duedate tardcost  MPM-Time
    1      3      0       50        0        0
************************************************************************
PRECEDENCE RELATIONS:
jobnr.    #modes  #successors   successors
   1        1          1           2
   2        1          1           3
   3        1          0
************************************************************************
REQUESTS/DURATIONS:
jobnr. mode  duration  R1 R2
  1     1       0       0  0
  2     1       5       1  0
  3     1       0       0  0
************************************************************************
RESOURCEAVAILABILITIES:
  R1   R2
   2    3
************************************************************************
"""
        with tempfile.NamedTemporaryFile(suffix=".sm", mode="w",
                                         delete=False, encoding="utf-8") as f:
            f.write(content)
            tmp_path = f.name
        try:
            inst = parse_psplib(tmp_path)
            # Jobs 1 and 3 are dummy source/sink (duration=0, zero demands)
            # and are stripped by the parser. Only job 2 (duration=5) remains.
            assert len(inst.tasks) == 1
            assert "J002" in inst.tasks
            assert inst.tasks["J002"].duration == 5
            assert inst.resource_capacities.get("R1") == 2
            assert inst.resource_capacities.get("R2") == 3
            assert inst.source == "psplib"
            assert inst.seed is None
            # J002 had only dummy predecessors (J001), so predecessors=[]
            assert inst.tasks["J002"].predecessors == []
        finally:
            os.unlink(tmp_path)
