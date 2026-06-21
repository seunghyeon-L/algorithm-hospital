# -*- coding: utf-8 -*-
"""jnuh5.py — 5-stage JNUH surgery scheduling (opponent-aligned comparison study).

Patient flow (5-stage DAG, identical structure to the opponent team):

        PRECHECK ┐
                 ├─> SURG ─> REC ─> DISCHARGE
        PREP ────┘

PRECHECK (수술 전 확인) and PREP (마취 준비) run in PARALLEL, both feeding SURG.
This is the opponent's exact graph, so the comparison is apples-to-apples.

Resources (ours + recovery bed):
  room(12) · staff/nurse(24) · anesthesia(8) · pacu_bed(18) · per-dept surgeons.

Stage durations (literature/Korean-grounded round values; see jnuh-arbitrary-values memory):
  PRECHECK tri(5,10,15)  PREP tri(10,20,40)  SURG literature-lognormal
  REC = clamp(0.2*SURG + tri(30,50,90), 35, 180)   DISCHARGE tri(30,60,120)

Two objectives (both computed; OPTIMISE one at a time):
  (1) unweighted  Σ_task  (start - ready)                    [our PINNED]
  (2) weighted    Σ_task  w(patient)·(start - ready)         [KTAS 16:8:4:2:1]

Wait is reported BOTH ways for comparison:
  ours      = Σ_task (start - ready)             (resource-contention, per-task)
  opponent  = Σ_patient (discharge_end - arrival - Σstage_dur)   (flow-based)
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from backend.app.model import Instance, Task, Schedule, TaskAssignment
from backend.app import graph as _graph
from backend.app.baseline import greedy_resource_schedule
from backend.app.data import _JNUH_SURGEONS, _JNUH_CASE_MIX, _lognormal_minutes

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STAGES = ["PRECHECK", "PREP", "SURG", "REC", "DISCHARGE"]
STAGE_ORDER = {s: i for i, s in enumerate(STAGES)}

# KTAS time-inverse convex weights (level 1 = most urgent).  16:8:4:2:1.
KTAS_WEIGHT = {1: 16, 2: 8, 3: 4, 4: 2, 5: 1}

WORKDAY_MIN = 8 * 60          # notional 8h workday for overtime metric (parity w/ opponent)

# Per-department surgery types: (label, mean_min, sd_min, surg_staff_demand, ktas_level)
# durations from operative-time literature; ktas from surgical-urgency mapping.
JNUH5_SURGERY_TYPES: Dict[str, List[Tuple[str, int, int, int, int]]] = {
    "surg_gs": [("충수절제술", 58, 21, 2, 1), ("담낭절제술", 87, 25, 2, 3),
                ("탈장교정술", 65, 20, 2, 5), ("대장절제술", 151, 60, 3, 3)],
    "surg_os": [("슬관절치환술", 92, 37, 3, 5), ("고관절치환술", 110, 40, 3, 3),
                ("골절정복술", 152, 80, 2, 2)],
    "surg_ns": [("추간판절제술", 135, 50, 3, 3), ("개두술", 169, 62, 3, 1)],
    "surg_obgy": [("제왕절개", 55, 15, 2, 1), ("자궁절제술", 79, 30, 2, 3)],
    "surg_oph": [("백내장수술", 30, 10, 1, 5), ("유리체절제술", 75, 25, 2, 4)],
    "surg_ent": [("편도절제술", 45, 15, 2, 5), ("부비동내시경수술", 90, 30, 2, 5)],
    "surg_uro": [("경요도절제술", 94, 40, 2, 5), ("요로결석제거술", 80, 30, 2, 3)],
    "surg_cs": [("폐엽절제술", 180, 60, 3, 2)],
    "surg_ps": [("피판재건술", 157, 70, 2, 4)],
}


@dataclass
class Patient:
    """Patient-level metadata used for objective weighting and reporting."""
    pid: str
    dept: str
    case_label: str
    ktas: int
    weight: int                       # KTAS_WEIGHT[ktas]
    arrival: int                      # release time of PRECHECK/PREP (minutes)
    is_emergency: bool
    target_completion: int            # for tardiness metric
    task_ids: Dict[str, str]          # stage -> task_id
    stage_dur: Dict[str, int]         # stage -> duration (for opponent wait def)


@dataclass
class Jnuh5Instance:
    """Bundle of the scheduling Instance + patient metadata."""
    instance: Instance
    patients: Dict[str, Patient]
    scenario: str
    emergency_arrival: int = 120


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def _tri(rng: random.Random, lo: int, mode: int, hi: int) -> int:
    return max(1, int(round(rng.triangular(lo, mode, hi))))


def generate_jnuh5_instance(
    n_patients: int = 8,
    seed: int = 42,
    *,
    scenario: str = "normal",
    n_rooms: int = 12,
    n_staff: int = 24,
    n_anesthesia: int = 8,
    n_pacu: int = 18,
    turnover: int = 20,
    include_emergency: bool = False,
    emergency_arrival: int = 120,
    arrival_window: Tuple[int, int] = (0, 90),
    arrival_step: int = 5,
) -> Jnuh5Instance:
    """Generate a 5-stage JNUH instance with `n_patients` electives (+1 emergency)."""
    if not (1 <= n_patients <= 5000):
        raise ValueError(f"n_patients={n_patients} out of range [1, 5000]")
    rng = random.Random(seed)

    depts = [d for d, _ in _JNUH_CASE_MIX]
    weights = [w for _, w in _JNUH_CASE_MIX]

    tasks: Dict[str, Task] = {}
    patients: Dict[str, Patient] = {}

    resource_caps: Dict[str, int] = {
        "room": n_rooms,
        "staff": n_staff,
        "anesthesia": n_anesthesia,
        "pacu_bed": n_pacu,
        **_JNUH_SURGEONS,
    }

    def add_patient(idx: int, *, emergency: bool) -> None:
        pid = (f"E{idx:03d}" if emergency else f"P{idx:03d}")
        if emergency:
            dept = "surg_gs"  # emergency general-surgery add-on
            label, mean, sd, surg_staff = "응급수술", 120, 50, 3
            ktas = 1
            arrival = emergency_arrival
        else:
            dept = rng.choices(depts, weights=weights, k=1)[0]
            label, mean, sd, surg_staff, ktas = rng.choice(JNUH5_SURGERY_TYPES[dept])
            lo, hi = arrival_window
            arrival = rng.randrange(lo // arrival_step, hi // arrival_step + 1) * arrival_step
        weight = KTAS_WEIGHT[ktas]

        # --- stage durations ---
        surg_dur = _lognormal_minutes(rng, mean, sd)
        dur = {
            "PRECHECK": _tri(rng, 5, 10, 15),
            "PREP": _tri(rng, 10, 20, 40),
            "SURG": surg_dur,
            "REC": min(180, max(35, int(round(0.2 * surg_dur + _tri(rng, 30, 50, 90))))),
            "DISCHARGE": _tri(rng, 30, 60, 120),
        }

        # --- stage resource demands ---
        demands = {
            "PRECHECK": {"staff": 1},
            "PREP": {"staff": 1, "anesthesia": 1},
            "SURG": {"room": 1, "staff": surg_staff, "anesthesia": 1, dept: 1},
            "REC": {"pacu_bed": 1, "staff": 1},
            "DISCHARGE": {"staff": 1},
        }
        # drop zero-capacity surgeon resources defensively
        demands["SURG"] = {r: d for r, d in demands["SURG"].items()
                           if resource_caps.get(r, 0) > 0}

        tids = {s: f"{pid}_{s}" for s in STAGES}
        for s in STAGES:
            preds: List[str] = []
            if s == "SURG":
                preds = [tids["PRECHECK"], tids["PREP"]]
            elif s == "REC":
                preds = [tids["SURG"]]
            elif s == "DISCHARGE":
                preds = [tids["REC"]]
            tasks[tids[s]] = Task(
                task_id=tids[s],
                duration=dur[s],
                resources=demands[s],
                predecessors=preds,
                label=f"{label}·{s}",
                patient_id=pid,
                # only the two roots carry the arrival release; downstream inherit
                release_time=(arrival if s in ("PRECHECK", "PREP") else 0),
            )

        target = arrival + (3 * 60 if emergency else 5 * 60)
        patients[pid] = Patient(
            pid=pid, dept=dept, case_label=label, ktas=ktas, weight=weight,
            arrival=arrival, is_emergency=emergency, target_completion=target,
            task_ids=tids, stage_dur=dur,
        )

    for p in range(n_patients):
        add_patient(p, emergency=False)
    if include_emergency:
        add_patient(n_patients, emergency=True)

    inst = Instance(
        instance_id=f"jnuh5-{scenario}-n{n_patients}-seed{seed}",
        tasks=tasks,
        resource_capacities=resource_caps,
        seed=seed,
        source="synthetic",
        turnover=turnover,
    )
    inst.validate()
    return Jnuh5Instance(instance=inst, patients=patients,
                         scenario=scenario, emergency_arrival=emergency_arrival)


# ---------------------------------------------------------------------------
# Decode + objective
# ---------------------------------------------------------------------------

def task_order(inst: Instance) -> List[str]:
    """A deterministic topological order (baseline / seeding anchor)."""
    return _graph.topological_order(inst)


def decode(inst: Instance, order: List[str], algo: str = "decoded") -> Schedule:
    """Serial-SGS decode of a priority `order` (general DAG, release-aware)."""
    return greedy_resource_schedule(inst, order, algo=algo)


def _ready(inst: Instance, sched: Schedule, tid: str) -> int:
    task = inst.tasks[tid]
    base = task.release_time
    if not task.predecessors:
        return base
    return max(base, max(sched.assignments[p].end for p in task.predecessors))


def objective_value(ji: Jnuh5Instance, sched: Schedule, *, weighted: bool) -> float:
    """The optimisation objective: Σ_task [w·]·(start - ready).

    weighted=False -> our PINNED unweighted Σwait.
    weighted=True  -> KTAS-weighted Σ w(patient)·wait.
    """
    inst = ji.instance
    total = 0.0
    for tid, a in sched.assignments.items():
        w = ji.patients[inst.tasks[tid].patient_id].weight if weighted else 1
        total += w * (a.start - _ready(inst, sched, tid))
    return total


def evaluate_order(ji: Jnuh5Instance, order: List[str], *, weighted: bool
                   ) -> Tuple[float, Schedule]:
    sched = decode(ji.instance, order)
    return objective_value(ji, sched, weighted=weighted), sched


# ---------------------------------------------------------------------------
# Full metric panel (both teams' definitions)
# ---------------------------------------------------------------------------

def patient_metrics(ji: Jnuh5Instance, sched: Schedule) -> Dict[str, float]:
    """Compute the full comparison panel — both wait definitions + all metrics."""
    inst, pts = ji.instance, ji.patients
    a = sched.assignments

    # ---- our per-task wait (start - ready) ----
    our_total = 0.0
    our_weighted = 0.0
    waits_per_task: List[int] = []
    for tid, asg in a.items():
        w = pts[inst.tasks[tid].patient_id].weight
        wt = asg.start - _ready(inst, sched, tid)
        waits_per_task.append(wt)
        our_total += wt
        our_weighted += w * wt

    # ---- opponent flow-based per-patient wait ----
    opp_total = 0.0
    opp_weighted = 0.0
    pre_total = 0.0
    pre_weighted = 0.0
    tardiness = 0.0
    patient_waits: List[float] = []
    emerg_wait = 0.0
    for pid, p in pts.items():
        disc_end = a[p.task_ids["DISCHARGE"]].end
        proc = sum(p.stage_dur.values())
        flow = max(0, disc_end - p.arrival)
        wait = max(0.0, flow - proc)
        patient_waits.append(wait)
        opp_total += wait
        opp_weighted += p.weight * wait
        # presurgery (opponent definition: subtract precheck+prep durations)
        surg_start = a[p.task_ids["SURG"]].start
        pre_proc = p.stage_dur["PRECHECK"] + p.stage_dur["PREP"]
        pre_w = max(0.0, surg_start - p.arrival - pre_proc)
        pre_total += pre_w
        pre_weighted += p.weight * pre_w
        tardiness += max(0.0, disc_end - p.target_completion)
        if p.is_emergency:
            emerg_wait = wait

    makespan = max(asg.end for asg in a.values())
    overtime = max(0.0, makespan - WORKDAY_MIN)

    # ---- utilisation ----
    util: Dict[str, float] = {}
    for res, cap in inst.resource_capacities.items():
        busy = sum(inst.tasks[t].resources.get(res, 0) * inst.tasks[t].duration
                   for t in inst.tasks)
        denom = cap * makespan
        util[res] = busy / denom if denom > 0 else 0.0

    n = len(pts)
    return {
        # our definition
        "our_total_wait": our_total,
        "our_weighted_wait": our_weighted,
        # opponent definition
        "opp_total_wait": opp_total,
        "opp_weighted_wait": opp_weighted,
        "presurgery_wait": pre_total,
        "weighted_presurgery_wait": pre_weighted,
        # patient-centric
        "avg_wait_per_patient": (opp_total / n) if n else 0.0,
        "max_patient_wait": max(patient_waits) if patient_waits else 0.0,
        "emergency_wait": emerg_wait,
        "tardiness": tardiness,
        # schedule
        "makespan": float(makespan),
        "overtime": overtime,
        "or_utilization": util.get("room", 0.0),
        "anesthesia_utilization": util.get("anesthesia", 0.0),
        "pacu_utilization": util.get("pacu_bed", 0.0),
        "staff_utilization": util.get("staff", 0.0),
        "n_patients": float(n),
        "n_tasks": float(len(inst.tasks)),
    }
