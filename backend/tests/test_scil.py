"""Tests for SCIL (SA-seeded CP-SAT hybrid) and the rcpsp hint_schedule arg."""

import pytest

from backend.app.baseline import schedule_baseline
from backend.app.data import generate_jnuh_instance
from backend.app.rcpsp import schedule_rcpsp
from backend.app.scil import schedule_scil


@pytest.fixture(scope="module")
def small_instance():
    # Small enough that CP-SAT reaches optimal well inside the budget.
    return generate_jnuh_instance(n_patients=8, seed=42)


class TestRcpspHintArg:
    def test_backward_compatible_without_hint(self, small_instance):
        sched = schedule_rcpsp(small_instance, time_limit_sec=10)
        sched.validate(small_instance)
        assert sched.algo == "rcpsp"

    def test_accepts_external_hint(self, small_instance):
        base = schedule_baseline(small_instance)
        sched = schedule_rcpsp(
            small_instance, time_limit_sec=10, hint_schedule=base
        )
        sched.validate(small_instance)
        # With a feasible hint the solver must do at least as well as it.
        assert sched.total_wait(small_instance) <= base.total_wait(small_instance)


class TestScil:
    def test_runs_validates_and_labels(self, small_instance):
        sched = schedule_scil(small_instance, time_limit_sec=10, outer_rounds=2)
        sched.validate(small_instance)
        assert sched.algo == "scil"
        assert sched.wall_clock_sec > 0

    def test_not_worse_than_baseline(self, small_instance):
        base = schedule_baseline(small_instance)
        scil = schedule_scil(small_instance, time_limit_sec=10, outer_rounds=2)
        assert scil.total_wait(small_instance) <= base.total_wait(small_instance)

    def test_single_round_works(self, small_instance):
        sched = schedule_scil(small_instance, time_limit_sec=6, outer_rounds=1)
        sched.validate(small_instance)

    def test_rejects_zero_rounds(self, small_instance):
        with pytest.raises(ValueError):
            schedule_scil(small_instance, outer_rounds=0)

    def test_reproducible_assignments(self):
        inst = generate_jnuh_instance(n_patients=6, seed=7)
        a = schedule_scil(inst, time_limit_sec=8, outer_rounds=1, random_seed=11)
        b = schedule_scil(inst, time_limit_sec=8, outer_rounds=1, random_seed=11)
        # Small instance reaches optimal inside the budget -> same Σwait.
        assert a.total_wait(inst) == b.total_wait(inst)
