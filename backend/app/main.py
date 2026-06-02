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

from .data import generate_instance, parse_psplib
from .model import Instance
from .baseline import schedule_baseline
from .rcpsp import schedule_rcpsp, DEFAULT_TIME_LIMIT_SEC, DEFAULT_RANDOM_SEED
from .ga import schedule_ga
from .sa import schedule_sa
from .metrics import evaluate
from . import graph as _graph


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


def _get_or_raise(instance_id: str) -> Instance:
    """Retrieve a cached instance or raise 404."""
    if instance_id not in _instance_cache:
        raise HTTPException(
            status_code=404,
            detail=f"Instance '{instance_id}' not found. "
                   "Create it first via POST /instances.",
        )
    return _instance_cache[instance_id]


# ---------------------------------------------------------------------------
# Pydantic request / response schemas
# ---------------------------------------------------------------------------

class GenerateInstanceRequest(BaseModel):
    n_tasks: int = Field(default=35, ge=1, le=200, description="Number of tasks (1–200)")
    seed: int = Field(default=42, description="RNG seed for reproducibility")
    n_rooms: int = Field(default=3, ge=1, le=20, description="Number of operating rooms")
    n_staff: int = Field(default=5, ge=1, le=50, description="Total staff capacity")
    edge_prob: float = Field(default=0.25, ge=0.0, le=1.0, description="Precedence edge probability")
    turnover: int = Field(default=20, ge=0, le=120, description="Room turnover/cleanup minutes between consecutive cases")


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
    # rcpsp / ga optional tuning
    time_limit_sec: float = Field(default=DEFAULT_TIME_LIMIT_SEC, ge=1.0)
    random_seed: int = Field(default=DEFAULT_RANDOM_SEED)
    ga_pop_size: int = Field(default=100, ge=10)
    ga_n_gen: int = Field(default=200, ge=1)


class CompareRequest(BaseModel):
    instance_id: str
    time_limit_sec: float = Field(
        default=DEFAULT_TIME_LIMIT_SEC,
        ge=1.0,
        description="Wall-clock budget for RCPSP and GA (fair comparison)",
    )
    random_seed: int = Field(default=DEFAULT_RANDOM_SEED)
    ga_pop_size: int = Field(default=100, ge=10)
    ga_n_gen: int = Field(default=200, ge=1)


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
    inst = generate_instance(
        n_tasks=req.n_tasks,
        seed=req.seed,
        n_rooms=req.n_rooms,
        n_staff=req.n_staff,
        edge_prob=req.edge_prob,
        turnover=req.turnover,
    )
    _instance_cache[inst.instance_id] = inst
    return _instance_to_out(inst)


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
    _VALID_ALGOS = {"baseline", "rcpsp", "ga", "sa"}
    if algo not in _VALID_ALGOS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown algo '{algo}'. Valid: {sorted(_VALID_ALGOS)}",
        )

    instance = _get_or_raise(req.instance_id)

    try:
        if algo == "baseline":
            sched = schedule_baseline(instance)
        elif algo == "rcpsp":
            sched = schedule_rcpsp(
                instance,
                time_limit_sec=req.time_limit_sec,
                random_seed=req.random_seed,
            )
        elif algo == "ga":
            sched = schedule_ga(
                instance,
                seed=req.random_seed,
                pop_size=req.ga_pop_size,
                n_gen=req.ga_n_gen,
                time_limit_sec=req.time_limit_sec,
            )
        else:  # sa
            sched = schedule_sa(
                instance,
                seed=req.random_seed,
                time_limit_sec=req.time_limit_sec,
            )
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return _schedule_to_out(sched, instance)


# ---------------------------------------------------------------------------
# Routes — /compare
# ---------------------------------------------------------------------------

@app.post("/compare", response_model=CompareResponse, tags=["compare"])
def compare_algorithms(req: CompareRequest):
    """Run baseline + rcpsp + ga on the same instance and return a full comparison.

    All three algorithms run with the same time_limit_sec budget (fair).
    Returns per-algorithm schedule + metrics + %improvement, plus the
    critical path (resource-free DAG lower bound) for visualisation.
    """
    instance = _get_or_raise(req.instance_id)

    # --- critical path (reference lower bound, not a scheduler) ---
    try:
        cp_length, cp_path = _graph.critical_path(instance)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Critical path computation failed: {exc}",
        )

    # --- run all three algorithms ---
    errors: List[str] = []
    schedules = {}

    # baseline (always fast)
    try:
        schedules["baseline"] = schedule_baseline(instance)
    except Exception as exc:
        errors.append(f"baseline: {exc}")

    # rcpsp
    try:
        schedules["rcpsp"] = schedule_rcpsp(
            instance,
            time_limit_sec=req.time_limit_sec,
            random_seed=req.random_seed,
        )
    except Exception as exc:
        errors.append(f"rcpsp: {exc}")

    # ga
    try:
        schedules["ga"] = schedule_ga(
            instance,
            seed=req.random_seed,
            pop_size=req.ga_pop_size,
            n_gen=req.ga_n_gen,
            time_limit_sec=req.time_limit_sec,
        )
    except Exception as exc:
        errors.append(f"ga: {exc}")

    # sa (simulated annealing) — trajectory-based metaheuristic
    try:
        schedules["sa"] = schedule_sa(
            instance,
            seed=req.random_seed,
            time_limit_sec=req.time_limit_sec,
        )
    except Exception as exc:
        errors.append(f"sa: {exc}")

    if not schedules:
        raise HTTPException(
            status_code=500,
            detail=f"All algorithms failed: {'; '.join(errors)}",
        )

    # --- evaluate with shared baseline_wait for %improvement ---
    baseline_wait: Optional[int] = None
    if "baseline" in schedules:
        baseline_wait = schedules["baseline"].total_wait(instance)

    results: Dict[str, AlgoResult] = {}
    for algo, sched in schedules.items():
        m = evaluate(
            sched,
            instance,
            baseline_wait=baseline_wait if algo != "baseline" else None,
        )
        if algo == "baseline" and baseline_wait is not None:
            # attach 0% improvement for the baseline itself
            from .metrics import ScheduleMetrics
            m = ScheduleMetrics(
                instance_id=m.instance_id,
                algo=m.algo,
                total_wait=m.total_wait,
                makespan=m.makespan,
                resource_utilization=m.resource_utilization,
                wall_clock_sec=m.wall_clock_sec,
                n_tasks=m.n_tasks,
                pct_improvement_vs_baseline=0.0,
                task_breakdown=m.task_breakdown,
            )
        results[algo] = AlgoResult(
            metrics=_metrics_to_out(m),
            schedule=_schedule_to_out(sched, instance),
        )

    # --- summary card (top-level convenience numbers) ---
    summary: Dict[str, Any] = {
        "critical_path_length": cp_length,
        "errors": errors,
    }
    for algo, res in results.items():
        summary[f"{algo}_total_wait"] = res.metrics.total_wait
        summary[f"{algo}_makespan"] = res.metrics.makespan
        summary[f"{algo}_wall_clock_sec"] = round(res.metrics.wall_clock_sec, 3)
        if res.metrics.pct_improvement_vs_baseline is not None:
            summary[f"{algo}_pct_improvement"] = round(
                res.metrics.pct_improvement_vs_baseline, 2
            )

    return CompareResponse(
        instance_id=instance.instance_id,
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
