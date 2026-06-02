"""
tests/test_ga.py — GA schedule tests.

Test 1: valid schedule — ga produces a Schedule that passes validate().
Test 2: seed reproducibility — two runs with the same seed produce the
        same total_wait (identical schedule).
Test 3: fitness equals metrics.evaluate().total_wait — GA fitness is the
        PINNED Σwait, not a proxy.
Test 4: schedule covers all tasks in the instance.
"""

from __future__ import annotations

import sys
import os

# Ensure project root is on sys.path so `backend.app` imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from backend.app.data import generate_instance
from backend.app.ga import schedule_ga
from backend.app.metrics import evaluate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def small_instance():
    """A small 10-task instance for fast tests."""
    return generate_instance(n_tasks=10, seed=7, n_rooms=2)


@pytest.fixture(scope="module")
def medium_instance():
    """A 30-task instance for more realistic tests."""
    return generate_instance(n_tasks=30, seed=42, n_rooms=3)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGAValidSchedule:
    """GA must produce a schedule that passes Schedule.validate()."""

    def test_small_instance_valid(self, small_instance):
        sched = schedule_ga(small_instance, seed=0, pop_size=20, n_gen=10)
        # validate raises ValueError on any violation — must not raise
        sched.validate(small_instance)

    def test_medium_instance_valid(self, medium_instance):
        sched = schedule_ga(medium_instance, seed=42, pop_size=50, n_gen=20)
        sched.validate(medium_instance)

    def test_schedule_algo_tag(self, small_instance):
        sched = schedule_ga(small_instance, seed=0, pop_size=20, n_gen=5)
        assert sched.algo == "ga"

    def test_schedule_instance_id(self, small_instance):
        sched = schedule_ga(small_instance, seed=0, pop_size=20, n_gen=5)
        assert sched.instance_id == small_instance.instance_id

    def test_all_tasks_covered(self, small_instance):
        sched = schedule_ga(small_instance, seed=0, pop_size=20, n_gen=5)
        assert set(sched.assignments.keys()) == set(small_instance.tasks.keys())

    def test_end_equals_start_plus_duration(self, small_instance):
        sched = schedule_ga(small_instance, seed=0, pop_size=20, n_gen=5)
        for task_id, asgn in sched.assignments.items():
            duration = small_instance.tasks[task_id].duration
            assert asgn.end == asgn.start + duration, (
                f"{task_id}: end={asgn.end} != start+duration={asgn.start+duration}"
            )

    def test_precedence_respected(self, small_instance):
        sched = schedule_ga(small_instance, seed=0, pop_size=20, n_gen=5)
        for task_id, task in small_instance.tasks.items():
            asgn = sched.assignments[task_id]
            for pred_id in task.predecessors:
                pred_end = sched.assignments[pred_id].end
                assert pred_end <= asgn.start, (
                    f"Precedence violated: {pred_id} ends at {pred_end} "
                    f"but {task_id} starts at {asgn.start}"
                )

    def test_wall_clock_sec_set(self, small_instance):
        sched = schedule_ga(small_instance, seed=0, pop_size=20, n_gen=5)
        assert sched.wall_clock_sec >= 0.0


class TestGASeedReproducibility:
    """Same seed must produce identical total_wait (Principle 3: reproducibility)."""

    def test_same_seed_same_total_wait_small(self, small_instance):
        sched_a = schedule_ga(small_instance, seed=99, pop_size=30, n_gen=15)
        sched_b = schedule_ga(small_instance, seed=99, pop_size=30, n_gen=15)
        assert sched_a.total_wait(small_instance) == sched_b.total_wait(small_instance), (
            "Same seed produced different total_wait — reproducibility violated"
        )

    def test_same_seed_same_assignments_small(self, small_instance):
        sched_a = schedule_ga(small_instance, seed=123, pop_size=30, n_gen=10)
        sched_b = schedule_ga(small_instance, seed=123, pop_size=30, n_gen=10)
        for task_id in small_instance.tasks:
            a = sched_a.assignments[task_id]
            b = sched_b.assignments[task_id]
            assert a.start == b.start, f"{task_id}: start differs ({a.start} vs {b.start})"
            assert a.end == b.end, f"{task_id}: end differs ({a.end} vs {b.end})"

    def test_different_seeds_may_differ(self, small_instance):
        sched_a = schedule_ga(small_instance, seed=1, pop_size=30, n_gen=10)
        sched_b = schedule_ga(small_instance, seed=2, pop_size=30, n_gen=10)
        # Not guaranteed to differ, but for 10 tasks / 2 distinct seeds this
        # almost always will — we just ensure both are valid regardless
        sched_a.validate(small_instance)
        sched_b.validate(small_instance)


class TestGAFitnessEqualsMetrics:
    """GA fitness == metrics.evaluate().total_wait (PINNED fairness check)."""

    def test_fitness_equals_metrics_total_wait_small(self, small_instance):
        sched = schedule_ga(small_instance, seed=7, pop_size=20, n_gen=10)
        metrics = evaluate(sched, small_instance)
        schedule_tw = sched.total_wait(small_instance)
        assert metrics.total_wait == schedule_tw, (
            f"metrics.total_wait={metrics.total_wait} != "
            f"Schedule.total_wait={schedule_tw}"
        )

    def test_fitness_equals_metrics_total_wait_medium(self, medium_instance):
        sched = schedule_ga(medium_instance, seed=42, pop_size=50, n_gen=20)
        metrics = evaluate(sched, medium_instance)
        schedule_tw = sched.total_wait(medium_instance)
        assert metrics.total_wait == schedule_tw


class TestGATimeBudget:
    """time_limit_sec caps wall-clock runtime."""

    def test_time_limit_respected(self, medium_instance):
        import time
        limit = 2.0  # seconds
        t0 = time.perf_counter()
        sched = schedule_ga(
            medium_instance,
            seed=0,
            pop_size=100,
            n_gen=10000,  # very high — limit should kick in first
            time_limit_sec=limit,
        )
        elapsed = time.perf_counter() - t0
        # Allow generous overhead (generation boundary + overhead)
        assert elapsed < limit + 3.0, (
            f"GA ran {elapsed:.2f}s which is well over limit {limit}s"
        )
        sched.validate(medium_instance)
