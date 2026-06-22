"""
main.py — FastAPI application for hospital surgery scheduling comparison.

Endpoints:
  GET  /instances              — list available (cached) instances
  POST /instances              — generate a new synthetic instance
  GET  /instances/{instance_id} — retrieve a specific instance as JSON
  POST /schedule/{algo}        — run one algorithm on an instance → Schedule + metrics
  POST /compare                — run baseline + rcpsp + ga on one instance → full comparison

All responses use Pydantic schemas for clean JSON serialisation.
No pandas/pyarrow imports (avoid Windows DLL collision).
CORS: allow all origins (frontend on localhost:3000).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .model import Instance
from .metrics import evaluate
from . import graph as _graph
from .jnuh5 import (
    generate_jnuh5_instance,
    Jnuh5Instance,
    objective_value,
    patient_metrics,
)
from .jnuh5_algos import run_algorithm

DEFAULT_TIME_LIMIT_SEC = 8.0
DEFAULT_RANDOM_SEED = 42

# Algorithms shown in the app (canonical jnuh5 names). These keys are used
# verbatim as the result-dict keys consumed by the frontend.
COMPARE_ALGOS = ["baseline", "SA", "GA-seeded", "HGA", "CP-SAT"]
SCHEDULE_ALGOS = {"baseline", "SA", "GA", "GA-seeded", "HGA", "CP-SAT", "SCIL"}


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Hospital Surgery Scheduling API",
    description=(
        "Compares baseline (greedy topological), RCPSP (OR-Tools CP-SAT), "
        "and GA (DEAP) on the same instance using the PINNED Σwait objective."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # frontend dev server (localhost:3000 etc.)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# In-memory instance cache (keyed by instance_id)
# ---------------------------------------------------------------------------

_instance_cache: Dict[str, Instance] = {}
_jnuh5_cache: Dict[str, Jnuh5Instance] = {}


def _get_or_raise(instance_id: str) -> Instance:
    """Retrieve a cached instance or raise 404."""
    if instance_id not in _instance_cache:
        raise HTTPException(
            status_code=404,
            detail=f"Instance '{instance_id}' not found. "
                   "Create it first via POST /instances.",
        )
    return _instance_cache[instance_id]


def _get_jnuh5_or_raise(instance_id: str) -> Jnuh5Instance:
    """Retrieve the cached Jnuh5Instance (keeps KTAS weights/patients) or raise 404."""
    if instance_id not in _jnuh5_cache:
        raise HTTPException(
            status_code=404,
            detail=f"Instance '{instance_id}' not found. Create it first via POST /instances.",
        )
    return _jnuh5_cache[instance_id]


# ---------------------------------------------------------------------------
# Pydantic request / response schemas
# ---------------------------------------------------------------------------

class GenerateInstanceRequest(BaseModel):
    n_patients: int = Field(default=8, ge=1, le=40, description="환자 수 (각 5단계 작업)")
    seed: int = Field(default=42, description="재현용 RNG 시드")
    n_rooms: int = Field(default=12, ge=1, le=20, description="수술실 수 (JNUH 평상 12 · 위기 8)")
    n_staff: int = Field(default=24, ge=1, le=80, description="간호·수술 인력")
    n_anesthesia: int = Field(default=8, ge=1, le=40, description="마취 자원")
    n_pacu: int = Field(default=18, ge=1, le=80, description="회복실 베드(PACU)")
    include_emergency: bool = Field(default=False, description="응급 1명 삽입(도착 t=120분)")
    turnover: int = Field(default=20, ge=0, le=120, description="수술실 전환시간(분)")


class TaskOut(BaseModel):
    task_id: str
    duration: int
    resources: Dict[str, int]
    predecessors: List[str]
    label: Optional[str]
    patient_id: Optional[str]


class InstanceOut(BaseModel):
    instance_id: str
    n_tasks: int
    resource_capacities: Dict[str, int]
    seed: Optional[int]
    source: str
    turnover: int = 0
    tasks: Dict[str, TaskOut]


class InstanceSummary(BaseModel):
    instance_id: str
    n_tasks: int
    resource_capacities: Dict[str, int]
    seed: Optional[int]
    source: str


class TaskAssignmentOut(BaseModel):
    task_id: str
    start: int
    end: int
    room: Optional[str]
    wait: int          # start - ready (PINNED)
    ready: int         # max predecessor end (precedence-only)


class ScheduleOut(BaseModel):
    instance_id: str
    algo: str
    wall_clock_sec: float
    total_wait: int
    makespan: int
    assignments: Dict[str, TaskAssignmentOut]


class ResourceUtilOut(BaseModel):
    pass  # dynamic keys — returned as plain dict


class MetricsOut(BaseModel):
    instance_id: str
    algo: str
    total_wait: int
    makespan: int
    resource_utilization: Dict[str, float]
    wall_clock_sec: float
    n_tasks: int
    pct_improvement_vs_baseline: Optional[float]


class CriticalPathOut(BaseModel):
    length: int
    task_ids: List[str]


class ScheduleRequest(BaseModel):
    instance_id: str
    time_limit_sec: float = Field(default=DEFAULT_TIME_LIMIT_SEC, ge=1.0, description="알고리즘당 시간 예산(초)")
    random_seed: int = Field(default=DEFAULT_RANDOM_SEED)
    weighted: bool = Field(default=False, description="True=KTAS 가중 목적, False=무가중 Σwait")


class CompareRequest(BaseModel):
    instance_id: str
    time_limit_sec: float = Field(
        default=DEFAULT_TIME_LIMIT_SEC, ge=1.0,
        description="각 알고리즘 공통 시간 예산(공정 비교)",
    )
    random_seed: int = Field(default=DEFAULT_RANDOM_SEED)
    weighted: bool = Field(default=False, description="True=KTAS 가중 목적, False=무가중 Σwait")


class AlgoResult(BaseModel):
    metrics: MetricsOut
    schedule: ScheduleOut


class CompareResponse(BaseModel):
    instance_id: str
    critical_path: CriticalPathOut
    results: Dict[str, AlgoResult]   # algo → result
    summary: Dict[str, Any]          # convenience top-level numbers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _instance_to_out(inst: Instance) -> InstanceOut:
    return InstanceOut(
        instance_id=inst.instance_id,
        n_tasks=len(inst.tasks),
        resource_capacities=inst.resource_capacities,
        seed=inst.seed,
        source=inst.source,
        turnover=getattr(inst, "turnover", 0),
        tasks={
            tid: TaskOut(
                task_id=t.task_id,
                duration=t.duration,
                resources=t.resources,
                predecessors=t.predecessors,
                label=t.label,
                patient_id=t.patient_id,
            )
            for tid, t in inst.tasks.items()
        },
    )


def _schedule_to_out(sched, instance: Instance) -> ScheduleOut:
    """Convert a Schedule to ScheduleOut, computing per-task wait/ready."""
    assignments_out: Dict[str, TaskAssignmentOut] = {}
    for task_id, asgn in sched.assignments.items():
        ready_time = asgn.ready(instance, sched)
        wait_time = asgn.wait(instance, sched)
        assignments_out[task_id] = TaskAssignmentOut(
            task_id=task_id,
            start=asgn.start,
            end=asgn.end,
            room=asgn.room,
            wait=wait_time,
            ready=ready_time,
        )
    return ScheduleOut(
        instance_id=sched.instance_id,
        algo=sched.algo,
        wall_clock_sec=sched.wall_clock_sec,
        total_wait=sched.total_wait(instance),
        makespan=sched.makespan(),
        assignments=assignments_out,
    )


def _metrics_to_out(m) -> MetricsOut:
    return MetricsOut(
        instance_id=m.instance_id,
        algo=m.algo,
        total_wait=m.total_wait,
        makespan=m.makespan,
        resource_utilization=m.resource_utilization,
        wall_clock_sec=m.wall_clock_sec,
        n_tasks=m.n_tasks,
        pct_improvement_vs_baseline=m.pct_improvement_vs_baseline,
    )


def _jnuh5_metrics_out(ji: Jnuh5Instance, sched, name: str, weighted: bool,
                       base_obj: Optional[float]) -> MetricsOut:
    """Metrics for a jnuh5 schedule. total_wait = chosen objective (weighted or not);
    resource_utilization/makespan via the generic evaluator."""
    inst = ji.instance
    obj = objective_value(ji, sched, weighted=weighted)
    gm = evaluate(sched, inst)  # generic: resource_utilization + makespan
    if name == "baseline":
        pct: Optional[float] = 0.0
    elif base_obj is None:
        pct = None
    elif base_obj <= 0:
        pct = 0.0          # baseline already optimal (0 wait) → nothing to improve
    else:
        pct = 100.0 * (base_obj - obj) / base_obj
    return MetricsOut(
        instance_id=inst.instance_id,
        algo=name,
        total_wait=int(round(obj)),
        makespan=int(gm.makespan),
        resource_utilization=gm.resource_utilization,
        wall_clock_sec=round(sched.wall_clock_sec, 3),
        n_tasks=len(inst.tasks),
        pct_improvement_vs_baseline=(round(pct, 2) if pct is not None else None),
    )


# ---------------------------------------------------------------------------
# Routes — /instances
# ---------------------------------------------------------------------------

@app.get("/instances", response_model=List[InstanceSummary], tags=["instances"])
def list_instances():
    """List all instances currently held in the server cache."""
    return [
        InstanceSummary(
            instance_id=inst.instance_id,
            n_tasks=len(inst.tasks),
            resource_capacities=inst.resource_capacities,
            seed=inst.seed,
            source=inst.source,
        )
        for inst in _instance_cache.values()
    ]


@app.post("/instances", response_model=InstanceOut, status_code=201, tags=["instances"])
def create_instance(req: GenerateInstanceRequest):
    """Generate a new synthetic instance and cache it.

    Returns the full instance (tasks + edges) for DAG visualisation.
    """
    ji = generate_jnuh5_instance(
        n_patients=req.n_patients,
        seed=req.seed,
        n_rooms=req.n_rooms,
        n_staff=req.n_staff,
        n_anesthesia=req.n_anesthesia,
        n_pacu=req.n_pacu,
        turnover=req.turnover,
        include_emergency=req.include_emergency,
    )
    _jnuh5_cache[ji.instance.instance_id] = ji
    _instance_cache[ji.instance.instance_id] = ji.instance
    return _instance_to_out(ji.instance)


@app.get("/instances/{instance_id}", response_model=InstanceOut, tags=["instances"])
def get_instance(instance_id: str):
    """Retrieve a cached instance by ID."""
    inst = _get_or_raise(instance_id)
    return _instance_to_out(inst)


# ---------------------------------------------------------------------------
# Routes — /schedule/{algo}
# ---------------------------------------------------------------------------

@app.post("/schedule/{algo}", response_model=ScheduleOut, tags=["schedule"])
def run_schedule(algo: str, req: ScheduleRequest):
    """Run a single algorithm on a cached instance.

    algo: one of 'baseline' | 'rcpsp' | 'ga'

    Returns the schedule with per-task start/end/room/wait.
    """
    if algo not in SCHEDULE_ALGOS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown algo '{algo}'. Valid: {sorted(SCHEDULE_ALGOS)}",
        )

    ji = _get_jnuh5_or_raise(req.instance_id)

    try:
        sched = run_algorithm(
            algo, ji, weighted=req.weighted,
            budget=req.time_limit_sec, seed=req.random_seed,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return _schedule_to_out(sched, ji.instance)


# ---------------------------------------------------------------------------
# Routes — /compare
# ---------------------------------------------------------------------------

@app.post("/compare", response_model=CompareResponse, tags=["compare"])
def compare_algorithms(req: CompareRequest):
    """우리 jnuh5 알고리즘(baseline·SA·GA-seeded·HGA·CP-SAT)을 같은 인스턴스에
    공통 시간 예산으로 실행하고, 선택한 목적(무가중 Σwait 또는 KTAS 가중)으로
    비교 결과를 반환한다. critical_path는 자원무시 DAG 하한(시각화용)."""
    ji = _get_jnuh5_or_raise(req.instance_id)
    inst = ji.instance

    # --- critical path (reference lower bound, not a scheduler) ---
    try:
        cp_length, cp_path = _graph.critical_path(inst)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Critical path computation failed: {exc}",
        )

    # --- run our 5 algorithms under one shared budget + chosen objective ---
    errors: List[str] = []
    schedules: Dict[str, Any] = {}
    for name in COMPARE_ALGOS:
        try:
            schedules[name] = run_algorithm(
                name, ji, weighted=req.weighted,
                budget=req.time_limit_sec, seed=req.random_seed,
            )
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    if not schedules:
        raise HTTPException(
            status_code=500,
            detail=f"All algorithms failed: {'; '.join(errors)}",
        )

    # baseline objective value = denominator for %improvement (same objective)
    base_obj = (objective_value(ji, schedules["baseline"], weighted=req.weighted)
                if "baseline" in schedules else None)

    results: Dict[str, AlgoResult] = {}
    for name, sched in schedules.items():
        results[name] = AlgoResult(
            metrics=_jnuh5_metrics_out(ji, sched, name, req.weighted, base_obj),
            schedule=_schedule_to_out(sched, inst),
        )

    # --- summary card (top-level convenience numbers) ---
    summary: Dict[str, Any] = {
        "critical_path_length": cp_length,
        "objective": "weighted" if req.weighted else "unweighted",
        "errors": errors,
    }
    for name, res in results.items():
        summary[f"{name}_total_wait"] = res.metrics.total_wait
        summary[f"{name}_makespan"] = res.metrics.makespan
        summary[f"{name}_wall_clock_sec"] = round(res.metrics.wall_clock_sec, 3)
        if res.metrics.pct_improvement_vs_baseline is not None:
            summary[f"{name}_pct_improvement"] = round(
                res.metrics.pct_improvement_vs_baseline, 2
            )

    return CompareResponse(
        instance_id=inst.instance_id,
        critical_path=CriticalPathOut(length=cp_length, task_ids=cp_path),
        results=results,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"])
def health():
    """Simple liveness probe."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Serve the built frontend (single-deploy on Hugging Face Spaces).
# The Docker build copies the Next.js static export into FRONTEND_DIR.
# Mounted LAST so all API routes above take precedence; only unmatched paths
# fall through to the static SPA. Skipped in local dev (dir absent → Next dev
# server serves the frontend separately on :3000).
# ---------------------------------------------------------------------------
import os as _os  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_FRONTEND_DIR = _os.environ.get(
    "FRONTEND_DIR",
    _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
        "frontend_static",
    ),
)
if _os.path.isdir(_FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
