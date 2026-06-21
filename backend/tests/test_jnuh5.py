# -*- coding: utf-8 -*-
"""Tests for the 5-stage JNUH comparison study (jnuh5 + jnuh5_algos + jnuh5_numba)."""
import numpy as np
import pytest

from backend.app.jnuh5 import (generate_jnuh5_instance, task_order, decode,
                               objective_value, patient_metrics, STAGES)
from backend.app import jnuh5_algos as A
from backend.scripts import jnuh5_numba as NB


# --------------------------------------------------------------------------- generation
def test_generate_structure():
    ji = generate_jnuh5_instance(8, seed=42, include_emergency=True)
    inst = ji.instance
    assert len(ji.patients) == 9                 # 8 electives + 1 emergency
    assert len(inst.tasks) == 9 * 5              # 5 stages each
    # SURG has exactly two predecessors (PRECHECK ∥ PREP)
    p = next(iter(ji.patients.values()))
    surg = inst.tasks[p.task_ids["SURG"]]
    assert set(surg.predecessors) == {p.task_ids["PRECHECK"], p.task_ids["PREP"]}
    assert inst.tasks[p.task_ids["REC"]].predecessors == [p.task_ids["SURG"]]
    # recovery bed + anesthesia resources exist
    assert "pacu_bed" in inst.resource_capacities
    assert "anesthesia" in inst.resource_capacities


def test_emergency_release():
    ji = generate_jnuh5_instance(8, seed=1, include_emergency=True, emergency_arrival=120)
    e = [p for p in ji.patients.values() if p.is_emergency][0]
    assert e.arrival == 120 and e.weight == 16   # KTAS-1 emergency
    sched = decode(ji.instance, task_order(ji.instance))
    assert sched.assignments[e.task_ids["PRECHECK"]].start >= 120


# --------------------------------------------------------------------------- decode / metrics
def test_decode_valid_and_waits_nonneg():
    ji = generate_jnuh5_instance(30, seed=3)
    sched = decode(ji.instance, task_order(ji.instance))
    sched.validate(ji.instance)                  # raises if precedence/release violated
    m = patient_metrics(ji, sched)
    assert m["our_total_wait"] >= 0 and m["opp_total_wait"] >= 0
    assert m["our_weighted_wait"] >= m["our_total_wait"]   # weights >= 1


def test_objective_weighted_ge_unweighted():
    ji = generate_jnuh5_instance(40, seed=5)
    sched = decode(ji.instance, task_order(ji.instance))
    u = objective_value(ji, sched, weighted=False)
    w = objective_value(ji, sched, weighted=True)
    assert w >= u >= 0


# --------------------------------------------------------------------------- algorithms anytime
@pytest.mark.parametrize("weighted", [False, True])
@pytest.mark.parametrize("name", ["SA", "GA", "GA-seeded", "HGA", "CP-SAT", "SCIL"])
def test_algorithm_anytime_not_worse_than_baseline(name, weighted):
    ji = generate_jnuh5_instance(25, seed=7)
    base = A.baseline(ji)
    base_obj = objective_value(ji, base, weighted=weighted)
    sched = A.run_algorithm(name, ji, weighted=weighted, budget=0.5, seed=7)
    sched.validate(ji.instance)
    obj = objective_value(ji, sched, weighted=weighted)
    assert obj <= base_obj + 1e-6, f"{name} worse than baseline: {obj} > {base_obj}"


# --------------------------------------------------------------------------- numba equivalence
@pytest.mark.parametrize("n", [20, 50])
def test_numba_decoder_matches_python(n):
    ji = generate_jnuh5_instance(n, seed=9, include_emergency=True)
    arr = NB.extract_arrays_5(ji)
    order = np.array([arr["idx"][t] for t in task_order(ji.instance)], np.int64)
    order_ids = [arr["tids"][i] for i in order]
    py_u = objective_value(ji, decode(ji.instance, order_ids), weighted=False)
    py_w = objective_value(ji, decode(ji.instance, order_ids), weighted=True)
    assert NB.decode_obj(arr, order, False) == py_u
    assert NB.decode_obj(arr, order, True) == py_w


# --------------------------------------------------------------------------- emergency dynamic
def test_dynamic_emergency_valid_and_frozen():
    sched, ji = A.solve_dynamic_emergency(20, 42, "GA-seeded", weighted=False, budget=0.4)
    sched.validate(ji.instance)
    # every task respects its (restored, arrival-anchored) release_time
    for t, task in ji.instance.tasks.items():
        assert sched.assignments[t].start >= task.release_time
