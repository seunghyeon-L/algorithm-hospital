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
