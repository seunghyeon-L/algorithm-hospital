"""
data.py — synthetic hospital DAG generator + PSPLIB (.sm) parser.

Synthetic generator:
  - Produces 30~50 tasks with seeded RNG (reproducible).
  - Tasks are labelled as hospital procedures (prep, surgery, recovery, etc.).
  - Precedence graph is a random DAG (no cycles by construction: edges only go
    from lower to higher task index).
  - Each task has a duration (5–120 min) and resource demands (room, staff).

PSPLIB parser:
  - Reads the standard .sm format used by j30/j60/j120 benchmark sets.
  - Returns an Instance with tasks, precedences, and resource capacities.
"""

from __future__ import annotations

import math
import random
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from .model import Instance, Task
except ImportError:
    from backend.app.model import Instance, Task  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Hospital procedure name pools (for realistic-looking labels)
# ---------------------------------------------------------------------------

_PROCEDURE_TYPES = [
    "Pre-op Assessment",
    "Anaesthesia Induction",
    "Surgical Prep",
    "Appendectomy",
    "Cholecystectomy",
    "Hernia Repair",
    "Knee Replacement",
    "Hip Replacement",
    "Spinal Fusion",
    "Cardiac Bypass",
    "Cataract Removal",
    "Tonsillectomy",
    "Endoscopy",
    "Colonoscopy",
    "Biopsy",
    "Wound Closure",
    "Recovery Room",
    "Post-op Monitoring",
    "Imaging (CT)",
    "Imaging (MRI)",
    "Lab Draw",
    "Medication Admin",
    "Physiotherapy Eval",
    "Discharge Assessment",
]


def _pick_label(rng: random.Random, idx: int) -> str:
    base = rng.choice(_PROCEDURE_TYPES)
    return f"{base} #{idx + 1}"


# ---------------------------------------------------------------------------
# Synthetic hospital DAG generator
# ---------------------------------------------------------------------------

def generate_instance(
    n_tasks: int = 35,
    seed: int = 42,
    n_rooms: int = 3,
    n_staff: int = 5,
    min_duration: int = 5,
    max_duration: int = 120,
    edge_prob: float = 0.25,
    turnover: int = 0,
) -> Instance:
    """Generate a reproducible synthetic hospital scheduling instance.

    Precedence edges go only from task i to task j where i < j, guaranteeing
    a DAG. Each task gets a random subset of predecessors from earlier tasks.

    Args:
        n_tasks:      Number of tasks (30–50 recommended).
        seed:         RNG seed for full reproducibility.
        n_rooms:      Total operating room capacity.
        n_staff:      Total surgical staff capacity.
        min_duration: Minimum task duration in minutes.
        max_duration: Maximum task duration in minutes.
        edge_prob:    Probability of adding an edge from any earlier task.

    Returns:
        Instance with instance_id 'synth-seed{seed}-n{n_tasks}'.
    """
    if not (1 <= n_tasks <= 200):
        raise ValueError(f"n_tasks={n_tasks} out of range [1, 200]")

    rng = random.Random(seed)
    tasks: Dict[str, Task] = {}

    for i in range(n_tasks):
        task_id = f"T{i:02d}"
        duration = rng.randint(min_duration, max_duration)
        room_demand = 1  # each task occupies exactly one room
        staff_demand = rng.randint(1, min(3, n_staff))

        # Predecessors: any subset of earlier tasks, controlled by edge_prob
        predecessors: List[str] = []
        for j in range(i):
            if rng.random() < edge_prob:
                predecessors.append(f"T{j:02d}")

        tasks[task_id] = Task(
            task_id=task_id,
            duration=duration,
            resources={"room": room_demand, "staff": staff_demand},
            predecessors=predecessors,
            label=_pick_label(rng, i),
            patient_id=f"P{i // 3:02d}",  # group ~3 tasks per patient
        )

    instance = Instance(
        instance_id=f"synth-seed{seed}-n{n_tasks}",
        tasks=tasks,
        resource_capacities={"room": n_rooms, "staff": n_staff},
        seed=seed,
        source="synthetic",
        turnover=turnover,
    )
    instance.validate()
    return instance


# ---------------------------------------------------------------------------
# JNUH (제주대학교병원) surgical-department instance generator
# ---------------------------------------------------------------------------
# Models the central operating suite (중앙수술부) of Jeju National University
# Hospital, surgical departments only.  Resource constants are sourced from
# the project research notes (.omc/ultragoal/notes/G1-research.md):
#   - room: 12 operating rooms (8 in crisis mode) — estimate: manual tally
#     from hospital website (2026.6), not press-verified; no primary source
#   - anesthesia: 8 anesthesiologists — estimate: concurrency upper-bound
#     assumption, no primary source (추정값: 동시수술 상한 가정, 1차 출처 미확보)
#   - per-department surgeon counts — estimate: manual tally from hospital
#     website (2026.6), not press-verified
# Surgery durations are drawn from lognormal distributions whose mean/SD come
# from published per-procedure / per-department operative-time studies
# (appendectomy 58±21, TKA 92±37, craniotomy ~169, dept means: ortho 152±92,
# general 151±98, neuro 135±92, uro 94±77, obgy 79±79 — see G1 notes).
# Per-type numbers below interpolate those sources; they are estimates, not
# hospital records.
#
# Each patient is a 3-task chain (exam -> surgery -> recovery), so Σwait keeps
# its PINNED meaning: start(task) - max(end of predecessors).
#
# The "room" key MUST stay literally "room": baseline.py/rcpsp.py hard-code it
# for turnover handling.  The dedicated-block variant therefore keeps
# room:12 and *adds* per-department "orblock_*" resources on top (their
# capacities sum to 12), which enforces departmental block limits without
# touching any algorithm code.

_JNUH_SURGEONS: Dict[str, int] = {
    "surg_gs": 11,   # 외과 (general surgery)
    "surg_os": 8,    # 정형외과 (orthopedics)
    "surg_obgy": 6,  # 산부인과
    "surg_oph": 6,   # 안과
    "surg_ns": 5,    # 신경외과
    "surg_ent": 5,   # 이비인후과
    "surg_uro": 4,   # 비뇨의학과
    "surg_cs": 1,    # 흉부외과 — scarce: hard local bottleneck
    "surg_ps": 1,    # 성형외과 — scarce: hard local bottleneck
}

# Realistic case-mix weights (NOT proportional to surgeon counts; cap=1
# departments get only a trickle so they act as local bottlenecks without
# trivialising the instance).
_JNUH_CASE_MIX: List[Tuple[str, float]] = [
    ("surg_gs", 0.24),
    ("surg_os", 0.20),
    ("surg_obgy", 0.12),
    ("surg_oph", 0.12),
    ("surg_ent", 0.10),
    ("surg_ns", 0.10),
    ("surg_uro", 0.08),
    ("surg_cs", 0.02),
    ("surg_ps", 0.02),
]

# Per-department surgery types: (label, mean_min, sd_min, staff_demand, priority_weight)
#
# Priority weight maps clinical urgency to a scheduling weight for the
# weighted_wait reporting metric (Σ wᵢ·waitᵢ).  It is a REPORTING METRIC
# ONLY — the optimisation objective (Σwait, unweighted) is NOT changed.
#
# Mapping rationale (based on KTAS / surgical triage conventions):
#   weight 10 — emergency: life-threatening if delayed hours
#                (cardiac bypass, emergent neurosurgery, ruptured-appendix)
#   weight  3 — urgent: deterioration likely within days if delayed
#                (most general-surgery cases, hip fracture repair, thoracic)
#   weight  1 — elective: stable; delay of days acceptable
#                (cataract, elective TKA, ENT procedures, plastics)
#
# Within each department, different procedure types may have different weights.
_JNUH_SURGERY_TYPES: Dict[str, List[Tuple[str, int, int, int, int]]] = {
    #                         label              mean  sd  staff  priority
    "surg_gs": [("충수절제술",      58,  21, 2, 10),  # appendectomy — urgent/emergent
                ("담낭절제술",      87,  25, 2,  3),  # cholecystectomy — urgent
                ("탈장교정술",      65,  20, 2,  1),  # hernia repair — elective
                ("대장절제술",     151,  60, 3,  3)], # colectomy — urgent
    "surg_os": [("슬관절치환술",    92,  37, 3,  1),  # TKA — elective
                ("고관절치환술",   110,  40, 3,  3),  # hip replacement — urgent (fracture)
                ("골절정복술",     152,  80, 2,  3)], # fracture fixation — urgent
    "surg_ns": [("추간판절제술",   135,  50, 3,  3),  # discectomy — urgent
                ("개두술",         169,  62, 3, 10)], # craniotomy — emergency
    "surg_obgy": [("제왕절개",      55,  15, 2, 10),  # C-section — emergency
                  ("자궁절제술",    79,  30, 2,  3)], # hysterectomy — urgent
    "surg_oph": [("백내장수술",     30,  10, 1,  1),  # cataract — elective
                 ("유리체절제술",   75,  25, 2,  3)], # vitrectomy — urgent
    "surg_ent": [("편도절제술",     45,  15, 2,  1),  # tonsillectomy — elective
                 ("부비동내시경수술", 90, 30, 2,  1)], # sinus endoscopy — elective
    "surg_uro": [("경요도절제술",   94,  40, 2,  1),  # TURP — elective
                 ("요로결석제거술", 80,  30, 2,  3)], # stone removal — urgent
    "surg_cs": [("폐엽절제술",    180,  60, 3,  3)],  # lobectomy — urgent
    "surg_ps": [("피판재건술",    157,  70, 2,  1)],  # flap reconstruction — elective
}

# Dedicated-block split of the 12 central rooms (sums to 12).  Thoracic and
# plastic surgery share the general-surgery block (no room of their own).
_JNUH_OR_BLOCKS: Dict[str, int] = {
    "orblock_gs": 3,
    "orblock_os": 3,
    "orblock_ns": 2,
    "orblock_obgy": 1,
    "orblock_oph": 1,
    "orblock_ent": 1,
    "orblock_uro": 1,
}

_JNUH_BLOCK_OF_DEPT: Dict[str, str] = {
    "surg_cs": "orblock_gs",
    "surg_ps": "orblock_gs",
}


def _lognormal_minutes(rng: random.Random, mean: int, sd: int,
                       lo: int = 15, hi: int = 420) -> int:
    """Draw a lognormal duration with the given mean/SD, clamped to [lo, hi]."""
    sigma2 = math.log(1.0 + (sd / mean) ** 2)
    sigma = sigma2 ** 0.5
    mu = math.log(mean) - sigma2 / 2.0
    value = rng.lognormvariate(mu, sigma)
    return max(lo, min(hi, int(round(value))))


def generate_jnuh_instance(
    n_patients: int = 20,
    seed: int = 42,
    crisis: bool = False,
    dedicated_blocks: bool = False,
    turnover: int = 20,
) -> Instance:
    """Generate a JNUH surgical-department instance (central OR suite).

    Args:
        n_patients:       Surgical patients to schedule (load knob; 20/50/100).
        seed:             RNG seed — fully reproducible.
        crisis:           True = crisis operation (room 12 -> 8, as reported
                          during the 2024 residency walkout).
        dedicated_blocks: False = pooled rooms (JNUH reality, 공용 풀).
                          True  = departmental block limits added on top
                          (orblock_* resources, capacities sum to 12).
        turnover:         Room cleanup/setup minutes between cases (default 20,
                          international benchmark 20–30).

    Returns:
        Instance with id 'jnuh-{normal|crisis}-{pool|block}-n{N}-seed{S}'.
        Each patient contributes 3 chained tasks:
          exam (staff only) -> surgery (room+staff+anesthesia+surgeon)
          -> recovery (staff only).
    """
    if not (1 <= n_patients <= 200):
        raise ValueError(f"n_patients={n_patients} out of range [1, 200]")

    rng = random.Random(seed)

    depts = [d for d, _ in _JNUH_CASE_MIX]
    weights = [w for _, w in _JNUH_CASE_MIX]

    tasks: Dict[str, Task] = {}

    for p in range(n_patients):
        pid = f"P{p:03d}"
        dept = rng.choices(depts, weights=weights, k=1)[0]
        # 5th tuple field (priority) is unused: the objective is unweighted Σwait.
        label, mean, sd, staff_demand, _priority = rng.choice(_JNUH_SURGERY_TYPES[dept])

        exam_id, surg_id, rec_id = f"{pid}_exam", f"{pid}_surg", f"{pid}_rec"

        tasks[exam_id] = Task(
            task_id=exam_id,
            duration=rng.randint(10, 20),
            resources={"staff": 1},
            predecessors=[],
            label=f"수술 전 검사 ({label})",
            patient_id=pid,
        )

        surgery_resources: Dict[str, int] = {
            "room": 1,
            "staff": staff_demand,
            "anesthesia": 1,
            dept: 1,
        }
        if dedicated_blocks:
            block = _JNUH_BLOCK_OF_DEPT.get(dept, "orblock_" + dept[5:])
            surgery_resources[block] = 1

        tasks[surg_id] = Task(
            task_id=surg_id,
            duration=_lognormal_minutes(rng, mean, sd),
            resources=surgery_resources,
            predecessors=[exam_id],
            label=label,
            patient_id=pid,
        )

        tasks[rec_id] = Task(
            task_id=rec_id,
            duration=rng.randint(20, 45),
            resources={"staff": 1},
            predecessors=[surg_id],
            label=f"회복실 ({label})",
            patient_id=pid,
        )

    resource_capacities: Dict[str, int] = {
        "room": 8 if crisis else 12,
        "staff": 24,        # nursing/support pool (estimate); bottleneck is anesthesia
        "anesthesia": 8,    # estimate: concurrency upper-bound, no primary source
        **_JNUH_SURGEONS,
    }
    if dedicated_blocks:
        # NOTE (modelling choices, intentional):
        #  - Under crisis the orblock split deliberately keeps the normal
        #    12-room allocation; the global room=8 capacity dominates, so the
        #    crisis-block cell is slightly looser per department than a true
        #    8-room block plan would be.
        #  - Turnover applies only to the global "room" pool (hard-coded in
        #    baseline.py/rcpsp.py); orblock_* enforces capacity, not cleanup.
        #    All algorithms see the same model, so comparisons remain fair.
        resource_capacities.update(_JNUH_OR_BLOCKS)

    mode = "crisis" if crisis else "normal"
    layout = "block" if dedicated_blocks else "pool"
    instance = Instance(
        instance_id=f"jnuh-{mode}-{layout}-n{n_patients}-seed{seed}",
        tasks=tasks,
        resource_capacities=resource_capacities,
        seed=seed,
        source="synthetic",
        turnover=turnover,
    )
    instance.validate()
    return instance


# ---------------------------------------------------------------------------
# PSPLIB (.sm) parser
# ---------------------------------------------------------------------------
# Reference format: http://www.om-db.wi.tum.de/psplib/files/sm_mslib.zip
# Sections used:
#   PRECEDENCE RELATIONS:  job_id  #modes  #successors  succ_list
#   REQUESTS/DURATIONS:    job_id  mode  duration  r1 r2 ...
#   RESOURCEAVAILABILITIES: R1 R2 ...
# ---------------------------------------------------------------------------

def parse_psplib(path: str | Path) -> Instance:
    """Parse a PSPLIB .sm file and return an Instance.

    Handles j30, j60, j120 benchmark files. Dummy source (job 1) and sink
    (last job) tasks are included as zero-duration tasks so the DAG structure
    is preserved; callers may filter them if desired.

    Args:
        path: Absolute or relative path to the .sm file.

    Returns:
        Instance with source='psplib', seed=None.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file cannot be parsed.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PSPLIB file not found: {path}")

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    # ---- locate section boundaries ----------------------------------------
    section_starts: Dict[str, int] = {}
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("PRECEDENCE RELATIONS"):
            section_starts["precedence"] = idx
        elif stripped.startswith("REQUESTS/DURATIONS"):
            section_starts["durations"] = idx
        elif stripped.startswith("RESOURCEAVAILABILITIES"):
            section_starts["resources"] = idx

    if not all(k in section_starts for k in ("precedence", "durations", "resources")):
        raise ValueError(
            f"Could not locate all required sections in {path.name}. "
            f"Found: {list(section_starts.keys())}"
        )

    # ---- parse resource availabilities -------------------------------------
    res_section_start = section_starts["resources"]
    # Skip header/separator lines to find the data line
    res_header_line: Optional[List[str]] = None
    res_values_line: Optional[List[str]] = None
    for line in lines[res_section_start + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            continue
        tokens = stripped.split()
        if all(re.match(r"R\s*\d+", t) for t in tokens):
            res_header_line = tokens
        elif res_header_line is not None and all(t.isdigit() for t in tokens):
            res_values_line = tokens
            break

    if res_header_line is None or res_values_line is None:
        raise ValueError("Could not parse RESOURCEAVAILABILITIES section")

    resource_names = [h.replace(" ", "") for h in res_header_line]
    resource_capacities: Dict[str, int] = {
        name: int(val) for name, val in zip(resource_names, res_values_line)
    }

    # ---- parse durations and resource demands ------------------------------
    dur_section_start = section_starts["durations"]
    # raw_tasks: job_num -> (duration, {res_name: demand})
    raw_tasks: Dict[int, Tuple[int, Dict[str, int]]] = {}

    for line in lines[dur_section_start + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("*") or stripped.startswith("-"):
            continue
        # Stop at next section header
        if stripped.isupper() and len(stripped.split()) <= 4:
            break
        tokens = stripped.split()
        # Format: jobnr  mode  duration  r1 r2 ...
        if len(tokens) < 3 + len(resource_names):
            continue
        try:
            job_nr = int(tokens[0])
            # mode = int(tokens[1])  # we only handle single-mode
            duration = int(tokens[2])
            demands: Dict[str, int] = {
                name: int(tokens[3 + i])
                for i, name in enumerate(resource_names)
            }
            raw_tasks[job_nr] = (duration, demands)
        except (ValueError, IndexError):
            continue

    if not raw_tasks:
        raise ValueError("Could not parse REQUESTS/DURATIONS section")

    # ---- parse precedence relations ----------------------------------------
    prec_section_start = section_starts["precedence"]
    # predecessors_of[job_nr] populated from successors lists
    successors_of: Dict[int, List[int]] = {k: [] for k in raw_tasks}

    for line in lines[prec_section_start + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("*") or stripped.startswith("-"):
            continue
        if stripped.isupper() and len(stripped.split()) <= 4:
            break
        tokens = stripped.split()
        # Format: jobnr  #modes  #successors  succ1 succ2 ...
        if len(tokens) < 3:
            continue
        try:
            job_nr = int(tokens[0])
            n_succ = int(tokens[2])
            succs = [int(tokens[3 + k]) for k in range(n_succ)]
            successors_of[job_nr] = succs
        except (ValueError, IndexError):
            continue

    # Build predecessor lists from successor lists
    predecessors_of: Dict[int, List[int]] = {k: [] for k in raw_tasks}
    for job_nr, succs in successors_of.items():
        for s in succs:
            if s in predecessors_of:
                predecessors_of[s].append(job_nr)

    # ---- identify and skip dummy source/sink tasks -------------------------
    # Standard PSPLIB always has a dummy source (job 1) and dummy sink (last
    # job) with duration=0 and all-zero resource demands.  We drop them and
    # rewire their predecessor/successor relationships so the remaining tasks
    # form a valid DAG with positive durations.

    dummy_jobs: set = set()
    for job_nr, (duration, demands) in raw_tasks.items():
        if duration == 0 and all(v == 0 for v in demands.values()):
            dummy_jobs.add(job_nr)

    # Transitively rewire: for each dummy job d with predecessors P and
    # successors S, add edges P->S to preserve dependency ordering.
    # (In practice source has no predecessors and sink has no successors.)
    for d in dummy_jobs:
        preds_of_d = predecessors_of.get(d, [])
        succs_of_d = successors_of.get(d, [])
        for s in succs_of_d:
            if s not in dummy_jobs:
                # Remove d from s's predecessor list
                predecessors_of[s] = [
                    p for p in predecessors_of.get(s, []) if p != d
                ]
                # Add d's own predecessors as predecessors of s
                for p in preds_of_d:
                    if p not in dummy_jobs and p not in predecessors_of[s]:
                        predecessors_of[s].append(p)

    # ---- assemble Instance -------------------------------------------------
    tasks: Dict[str, Task] = {}
    instance_id = f"psplib-{path.stem}"

    for job_nr in sorted(raw_tasks.keys()):
        if job_nr in dummy_jobs:
            continue  # skip source/sink dummies
        duration, demands = raw_tasks[job_nr]
        task_id = f"J{job_nr:03d}"
        # Only include predecessors that are real (non-dummy) tasks
        predecessors = [
            f"J{p:03d}"
            for p in predecessors_of.get(job_nr, [])
            if p not in dummy_jobs
        ]
        tasks[task_id] = Task(
            task_id=task_id,
            duration=duration,
            resources=demands,
            predecessors=predecessors,
            label=f"Job {job_nr}",
        )

    instance = Instance(
        instance_id=instance_id,
        tasks=tasks,
        resource_capacities=resource_capacities,
        seed=None,
        source="psplib",
    )
    instance.validate()
    return instance
