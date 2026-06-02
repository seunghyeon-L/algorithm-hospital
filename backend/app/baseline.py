"""
baseline.py — topological-sort order + greedy list-scheduling.

This is the *intentional naive baseline* for fair comparison.
It does NOT minimise Σ wait(task); it dispatches tasks in topological order
to the earliest time that is resource-feasible.

IMPORTANT (fair comparison — consensus Principle 2):
  The greedy decoder respects EVERY resource in instance.resource_capacities
  (both 'room' AND 'staff'), exactly like rcpsp.py's CP-SAT model.  This is
  shared by GA (ga.py imports greedy_resource_schedule) so that baseline, GA
  and RCPSP all solve the *same* constrained problem.

TURNOVER (real-world OR cleanup time):
  A room is held for `instance.turnover` extra minutes AFTER a case ends
  (cleaning/prep) before the next case can use it.  So a room is occupied
  during [start, end + turnover).  Turnover affects room availability ONLY —
  the wait definition (start − ready, precedence-only) is unchanged, so the
  comparison stays fair across all three algorithms.

Output: Schedule(algo='baseline') — valid per Schedule.validate().
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from backend.app.model import Instance, Schedule, TaskAssignment
from backend.app import graph as _graph  # graph.topological_order is required


# ---------------------------------------------------------------------------
# Shared resource-feasible greedy decoder (used by baseline AND ga.py)
# ---------------------------------------------------------------------------

# One scheduled interval: (start, end, room_release, demands, room_name)
#   end          — when the case finishes (staff free, makespan)
#   room_release — end + turnover (when the room is free for the next case)
_Interval = Tuple[int, int, int, Dict[str, int], str]


def _res_end(iv: _Interval, res: str) -> int:
    """Effective release time of interval *iv* for resource *res*.

    The 'room' resource is held until room_release (end + turnover);
    every other resource (e.g. 'staff') is released at end.
    """
    return iv[2] if res == "room" else iv[1]


def _usage_at(t: int, scheduled: List[_Interval], res: str) -> int:
    """Total demand for *res* by intervals covering instant t."""
    return sum(iv[3].get(res, 0) for iv in scheduled if iv[0] <= t < _res_end(iv, res))


def _feasible(
    start: int,
    duration: int,
    demands: Dict[str, int],
    scheduled: List[_Interval],
    capacities: Dict[str, int],
    turnover: int,
) -> bool:
    """True if placing a task at *start* respects all capacities (incl. turnover)."""
    end = start + duration
    for res, cap in capacities.items():
        dem = demands.get(res, 0)
        if dem == 0:
            continue
        occ_end = end + turnover if res == "room" else end
        # Usage only changes at interval boundaries; check the candidate start
        # plus every scheduled start that falls inside the candidate's occupancy.
        points = {start}
        for iv in scheduled:
            if start < iv[0] < occ_end:
                points.add(iv[0])
        for p in points:
            if _usage_at(p, scheduled, res) + dem > cap:
                return False
    return True


def _earliest_feasible_start(
    ready: int,
    duration: int,
    demands: Dict[str, int],
    scheduled: List[_Interval],
    capacities: Dict[str, int],
    turnover: int,
) -> int:
    """Earliest start >= ready that is resource-feasible for the whole duration."""
    candidates = {ready}
    for iv in scheduled:
        if iv[1] >= ready:
            candidates.add(iv[1])  # a case ends → staff frees
        if iv[2] >= ready:
            candidates.add(iv[2])  # room turnover ends → room frees
    for t in sorted(candidates):
        if _feasible(t, duration, demands, scheduled, capacities, turnover):
            return t
    return max([ready] + [iv[2] for iv in scheduled])


def _pick_room(
    start: int, end: int, turnover: int, scheduled: List[_Interval], room_names: List[str]
) -> str:
    """Pick a room not occupied (incl. turnover) during [start, end + turnover)."""
    occ_end = end + turnover
    busy = set()
    for iv in scheduled:
        # room iv occupies [iv.start, iv.room_release); new occupies [start, occ_end)
        if not (iv[2] <= start or iv[0] >= occ_end):
            busy.add(iv[4])
    for r in room_names:
        if r not in busy:
            return r
    return room_names[0]  # defensive; should not happen when room capacity holds


def greedy_resource_schedule(
    instance: Instance, order: List[str], algo: str = "baseline"
) -> Schedule:
    """Resource-feasible greedy list-scheduling from a priority *order*.

    Respects precedence, every resource in resource_capacities, AND room
    turnover.  Shared by baseline (order = topological) and GA (evolved perm).
    """
    caps = instance.resource_capacities
    turnover: int = getattr(instance, "turnover", 0) or 0
    num_rooms: int = caps.get("room", 3)
    room_names: List[str] = [f"room-{i + 1}" for i in range(num_rooms)]

    scheduled: List[_Interval] = []
    finished: Dict[str, int] = {}
    assignments: Dict[str, TaskAssignment] = {}

    remaining = [tid for tid in order if tid in instance.tasks]
    for tid in instance.tasks:
        if tid not in remaining:
            remaining.append(tid)

    max_passes = len(remaining) * len(remaining) + 1
    passes = 0
    while remaining and passes < max_passes:
        passes += 1
        progressed = False
        still: List[str] = []
        for task_id in remaining:
            task = instance.tasks[task_id]
            if not all(p in finished for p in task.predecessors):
                still.append(task_id)
                continue

            ready_time = (
                max((finished[p] for p in task.predecessors), default=0)
                if task.predecessors
                else 0
            )
            demands = task.resources if task.resources else {"room": 1}
            start = _earliest_feasible_start(
                ready_time, task.duration, demands, scheduled, caps, turnover
            )
            end = start + task.duration
            room = _pick_room(start, end, turnover, scheduled, room_names)

            scheduled.append((start, end, end + turnover, demands, room))
            finished[task_id] = end
            assignments[task_id] = TaskAssignment(
                task_id=task_id, start=start, end=end, room=room
            )
            progressed = True
        remaining = still
        if not progressed:
            break  # unresolvable (cycle) — should not happen on a valid DAG

    if remaining:
        max_time = max(finished.values(), default=0)
        for task_id in remaining:
            task = instance.tasks[task_id]
            start, end = max_time, max_time + task.duration
            assignments[task_id] = TaskAssignment(
                task_id=task_id, start=start, end=end, room=room_names[0]
            )
            finished[task_id] = end
            max_time = end + turnover

    return Schedule(
        instance_id=instance.instance_id,
        algo=algo,
        assignments=assignments,
        wall_clock_sec=0.0,
    )


def schedule_baseline(instance: Instance) -> Schedule:
    """Produce a naive resource-feasible greedy schedule for *instance*.

    Uses topological order from graph.py and dispatches each task to the
    earliest resource-feasible start (rooms AND staff AND turnover enforced).
    """
    t0 = time.perf_counter()
    instance.validate()

    topo_order: List[str] = _graph.topological_order(instance)
    sched = greedy_resource_schedule(instance, topo_order, algo="baseline")
    sched.wall_clock_sec = time.perf_counter() - t0

    sched.validate(instance)
    return sched
