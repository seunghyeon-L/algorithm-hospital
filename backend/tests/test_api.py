"""
tests/test_api.py — FastAPI endpoint tests (JNUH 5-stage integration).

Coverage:
  - GET  /health
  - POST /instances  (jnuh5 5-stage: PRECHECK∥PREP→SURG→REC→DISCHARGE, room=12)
  - GET  /instances, /instances/{id}
  - POST /schedule/{algo} for baseline · SA · GA-seeded · HGA · CP-SAT
  - POST /compare — 5-way comparison, both objectives (무가중 / KTAS 가중)
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app, _instance_cache, _jnuh5_cache

client = TestClient(app)

# 8 patients × 5 stages = 40 tasks; room fixed at JNUH 12.
SMALL_PAYLOAD = {"n_patients": 8, "seed": 7, "n_rooms": 12}
ALGOS = {"baseline", "SA", "GA-seeded", "HGA", "CP-SAT"}


@pytest.fixture(autouse=True)
def clear_cache():
    _instance_cache.clear()
    _jnuh5_cache.clear()
    yield
    _instance_cache.clear()
    _jnuh5_cache.clear()


@pytest.fixture
def created_instance_id():
    resp = client.post("/instances", json=SMALL_PAYLOAD)
    assert resp.status_code == 201, resp.text
    return resp.json()["instance_id"]


class TestHealth:
    def test_health_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestInstances:
    def test_create_instance_201(self):
        resp = client.post("/instances", json=SMALL_PAYLOAD)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["n_tasks"] == 40          # 8 patients × 5 stages
        assert len(data["tasks"]) == 40
        assert "instance_id" in data

    def test_jnuh5_resources(self):
        caps = client.post("/instances", json=SMALL_PAYLOAD).json()["resource_capacities"]
        assert caps["room"] == 12
        assert caps["staff"] == 24          # 주간 동시 ≈12실×2명 (FOIA 43명 3교대·주간집중)
        assert caps["anesthesia"] == 9      # FOIA 마취 전문의 9
        assert caps["pacu_bed"] == 18

    def test_five_stage_labels(self, created_instance_id):
        tasks = client.get(f"/instances/{created_instance_id}").json()["tasks"]
        stages = {t["label"].split("·")[-1] for t in tasks.values()}
        assert stages == {"PRECHECK", "PREP", "SURG", "REC", "DISCHARGE"}

    def test_crisis_rooms_8(self):
        caps = client.post("/instances", json={"n_patients": 6, "seed": 1, "n_rooms": 8}
                           ).json()["resource_capacities"]
        assert caps["room"] == 8

    def test_list_empty(self):
        assert client.get("/instances").json() == []

    def test_list_after_create(self, created_instance_id):
        ids = [i["instance_id"] for i in client.get("/instances").json()]
        assert created_instance_id in ids

    def test_get_instance_ok(self, created_instance_id):
        resp = client.get(f"/instances/{created_instance_id}")
        assert resp.status_code == 200
        assert resp.json()["instance_id"] == created_instance_id

    def test_get_instance_404(self):
        assert client.get("/instances/nonexistent-id").status_code == 404


class TestSchedule:
    def _req(self, instance_id: str, weighted: bool = False) -> dict:
        return {"instance_id": instance_id, "time_limit_sec": 1.0,
                "random_seed": 42, "weighted": weighted}

    @pytest.mark.parametrize("algo", sorted(ALGOS))
    def test_each_algo_200(self, created_instance_id, algo):
        resp = client.post(f"/schedule/{algo}", json=self._req(created_instance_id))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total_wait"] >= 0
        assert data["makespan"] > 0
        assert len(data["assignments"]) == 40

    def test_schedule_assignments_have_wait_ready(self, created_instance_id):
        data = client.post("/schedule/baseline", json=self._req(created_instance_id)).json()
        for asgn in data["assignments"].values():
            assert "wait" in asgn and "ready" in asgn
            assert asgn["wait"] >= 0
            assert asgn["end"] >= asgn["start"]

    def test_invalid_algo_422(self, created_instance_id):
        assert client.post("/schedule/unknown",
                           json=self._req(created_instance_id)).status_code == 422

    def test_missing_instance_404(self):
        assert client.post("/schedule/baseline",
                           json=self._req("no-such-id")).status_code == 404


class TestCompare:
    def _req(self, instance_id: str, weighted: bool = False) -> dict:
        return {"instance_id": instance_id, "time_limit_sec": 1.0,
                "random_seed": 42, "weighted": weighted}

    def test_compare_has_all_algos(self, created_instance_id):
        data = client.post("/compare", json=self._req(created_instance_id)).json()
        assert set(data["results"].keys()) == ALGOS

    def test_each_result_has_metrics_and_schedule(self, created_instance_id):
        data = client.post("/compare", json=self._req(created_instance_id)).json()
        for algo, result in data["results"].items():
            assert "metrics" in result and "schedule" in result

    def test_metrics_keys(self, created_instance_id):
        data = client.post("/compare", json=self._req(created_instance_id)).json()
        required = {"total_wait", "makespan", "wall_clock_sec", "n_tasks",
                    "resource_utilization", "pct_improvement_vs_baseline"}
        for algo, result in data["results"].items():
            assert not (required - set(result["metrics"].keys())), algo

    def test_baseline_pct_zero(self, created_instance_id):
        data = client.post("/compare", json=self._req(created_instance_id)).json()
        assert data["results"]["baseline"]["metrics"]["pct_improvement_vs_baseline"] == 0.0

    def test_critical_path(self, created_instance_id):
        cp = client.post("/compare", json=self._req(created_instance_id)).json()["critical_path"]
        assert cp["length"] > 0
        assert len(cp["task_ids"]) >= 1

    def test_summary_keys(self, created_instance_id):
        summary = client.post("/compare", json=self._req(created_instance_id)).json()["summary"]
        assert "baseline_total_wait" in summary
        assert "GA-seeded_total_wait" in summary
        assert "CP-SAT_total_wait" in summary
        assert summary["objective"] == "unweighted"

    def test_weighted_objective(self, created_instance_id):
        summary = client.post("/compare",
                              json=self._req(created_instance_id, weighted=True)
                              ).json()["summary"]
        assert summary["objective"] == "weighted"

    def test_total_waits_non_negative(self, created_instance_id):
        data = client.post("/compare", json=self._req(created_instance_id)).json()
        for algo, result in data["results"].items():
            assert result["metrics"]["total_wait"] >= 0

    def test_missing_instance_404(self):
        assert client.post("/compare", json=self._req("no-such-id")).status_code == 404

    def test_instance_id_in_response(self, created_instance_id):
        data = client.post("/compare", json=self._req(created_instance_id)).json()
        assert data["instance_id"] == created_instance_id
