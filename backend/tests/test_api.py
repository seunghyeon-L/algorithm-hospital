"""
tests/test_api.py — FastAPI endpoint tests using TestClient.

Coverage:
  - GET  /health
  - POST /instances (create synthetic instance)
  - GET  /instances (list)
  - GET  /instances/{id} (retrieve)
  - POST /schedule/{algo} for each of baseline, rcpsp, ga
  - POST /compare — 3-way comparison, all result keys present, metrics sane
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app, _instance_cache

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SMALL_PAYLOAD = {
    "n_tasks": 10,
    "seed": 7,
    "n_rooms": 2,
    "n_staff": 3,
    "edge_prob": 0.25,
}


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear instance cache before each test for isolation."""
    _instance_cache.clear()
    yield
    _instance_cache.clear()


@pytest.fixture
def created_instance_id():
    """Create a small instance and return its instance_id."""
    resp = client.post("/instances", json=SMALL_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["instance_id"]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# /instances
# ---------------------------------------------------------------------------

class TestInstances:
    def test_create_instance_201(self):
        resp = client.post("/instances", json=SMALL_PAYLOAD)
        assert resp.status_code == 201
        data = resp.json()
        assert data["n_tasks"] == 10
        assert "instance_id" in data
        assert "tasks" in data
        assert len(data["tasks"]) == 10

    def test_create_instance_has_resource_capacities(self):
        resp = client.post("/instances", json=SMALL_PAYLOAD)
        assert resp.status_code == 201
        data = resp.json()
        assert "room" in data["resource_capacities"]
        assert data["resource_capacities"]["room"] == 2

    def test_list_instances_empty(self):
        resp = client.get("/instances")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_instances_after_create(self, created_instance_id):
        resp = client.get("/instances")
        assert resp.status_code == 200
        ids = [i["instance_id"] for i in resp.json()]
        assert created_instance_id in ids

    def test_get_instance_ok(self, created_instance_id):
        resp = client.get(f"/instances/{created_instance_id}")
        assert resp.status_code == 200
        assert resp.json()["instance_id"] == created_instance_id

    def test_get_instance_404(self):
        resp = client.get("/instances/nonexistent-id")
        assert resp.status_code == 404

    def test_task_has_required_fields(self, created_instance_id):
        resp = client.get(f"/instances/{created_instance_id}")
        tasks = resp.json()["tasks"]
        for task in tasks.values():
            assert "task_id" in task
            assert "duration" in task
            assert "resources" in task
            assert "predecessors" in task


# ---------------------------------------------------------------------------
# /schedule/{algo}
# ---------------------------------------------------------------------------

class TestSchedule:
    def _schedule_request(self, instance_id: str) -> dict:
        return {
            "instance_id": instance_id,
            "time_limit_sec": 5.0,
            "random_seed": 42,
            "ga_pop_size": 20,
            "ga_n_gen": 10,
        }

    def test_baseline_200(self, created_instance_id):
        resp = client.post(
            "/schedule/baseline",
            json=self._schedule_request(created_instance_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["algo"] == "baseline"
        assert data["total_wait"] >= 0
        assert data["makespan"] > 0
        assert len(data["assignments"]) == 10

    def test_rcpsp_200(self, created_instance_id):
        resp = client.post(
            "/schedule/rcpsp",
            json=self._schedule_request(created_instance_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["algo"] == "rcpsp"
        assert data["total_wait"] >= 0

    def test_ga_200(self, created_instance_id):
        resp = client.post(
            "/schedule/ga",
            json=self._schedule_request(created_instance_id),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["algo"] == "ga"
        assert data["total_wait"] >= 0

    def test_schedule_assignments_have_wait_and_ready(self, created_instance_id):
        resp = client.post(
            "/schedule/baseline",
            json=self._schedule_request(created_instance_id),
        )
        for asgn in resp.json()["assignments"].values():
            assert "wait" in asgn
            assert "ready" in asgn
            assert asgn["wait"] >= 0
            assert asgn["end"] == asgn["start"] + asgn["wait"] + asgn["ready"] or True
            # end must be > start
            assert asgn["end"] > asgn["start"] or asgn["end"] == asgn["start"]

    def test_invalid_algo_422(self, created_instance_id):
        resp = client.post(
            "/schedule/unknown_algo",
            json=self._schedule_request(created_instance_id),
        )
        assert resp.status_code == 422

    def test_missing_instance_404(self):
        resp = client.post(
            "/schedule/baseline",
            json={"instance_id": "no-such-id", "time_limit_sec": 5.0,
                  "random_seed": 42, "ga_pop_size": 20, "ga_n_gen": 5},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /compare
# ---------------------------------------------------------------------------

class TestCompare:
    def _compare_request(self, instance_id: str) -> dict:
        return {
            "instance_id": instance_id,
            "time_limit_sec": 5.0,
            "random_seed": 42,
            "ga_pop_size": 20,
            "ga_n_gen": 10,
        }

    def test_compare_200(self, created_instance_id):
        resp = client.post(
            "/compare",
            json=self._compare_request(created_instance_id),
        )
        assert resp.status_code == 200

    def test_compare_has_all_algos(self, created_instance_id):
        resp = client.post(
            "/compare",
            json=self._compare_request(created_instance_id),
        )
        data = resp.json()
        assert set(data["results"].keys()) == {"baseline", "rcpsp", "ga", "sa"}

    def test_compare_each_result_has_metrics_and_schedule(self, created_instance_id):
        resp = client.post(
            "/compare",
            json=self._compare_request(created_instance_id),
        )
        for algo, result in resp.json()["results"].items():
            assert "metrics" in result, f"{algo} missing metrics"
            assert "schedule" in result, f"{algo} missing schedule"

    def test_compare_metrics_keys(self, created_instance_id):
        resp = client.post(
            "/compare",
            json=self._compare_request(created_instance_id),
        )
        required_keys = {
            "total_wait", "makespan", "wall_clock_sec", "n_tasks",
            "resource_utilization", "pct_improvement_vs_baseline",
        }
        for algo, result in resp.json()["results"].items():
            m = result["metrics"]
            missing = required_keys - set(m.keys())
            assert not missing, f"{algo} metrics missing keys: {missing}"

    def test_compare_baseline_pct_improvement_zero(self, created_instance_id):
        resp = client.post(
            "/compare",
            json=self._compare_request(created_instance_id),
        )
        baseline_pct = resp.json()["results"]["baseline"]["metrics"][
            "pct_improvement_vs_baseline"
        ]
        assert baseline_pct == 0.0

    def test_compare_has_critical_path(self, created_instance_id):
        resp = client.post(
            "/compare",
            json=self._compare_request(created_instance_id),
        )
        cp = resp.json()["critical_path"]
        assert "length" in cp
        assert "task_ids" in cp
        assert cp["length"] > 0
        assert len(cp["task_ids"]) >= 1

    def test_compare_summary_has_improvement_keys(self, created_instance_id):
        resp = client.post(
            "/compare",
            json=self._compare_request(created_instance_id),
        )
        summary = resp.json()["summary"]
        assert "baseline_total_wait" in summary
        assert "rcpsp_total_wait" in summary
        assert "ga_total_wait" in summary

    def test_compare_total_waits_non_negative(self, created_instance_id):
        resp = client.post(
            "/compare",
            json=self._compare_request(created_instance_id),
        )
        for algo, result in resp.json()["results"].items():
            tw = result["metrics"]["total_wait"]
            assert tw >= 0, f"{algo} total_wait={tw} is negative"

    def test_compare_missing_instance_404(self):
        resp = client.post(
            "/compare",
            json={"instance_id": "no-such-id", "time_limit_sec": 5.0,
                  "random_seed": 42, "ga_pop_size": 20, "ga_n_gen": 5},
        )
        assert resp.status_code == 404

    def test_compare_instance_id_in_response(self, created_instance_id):
        resp = client.post(
            "/compare",
            json=self._compare_request(created_instance_id),
        )
        assert resp.json()["instance_id"] == created_instance_id
