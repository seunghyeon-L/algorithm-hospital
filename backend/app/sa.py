"""
sa.py — Simulated Annealing (시뮬레이티드 어닐링) for surgery scheduling.

GA(군집 기반)·RCPSP(정확해)와 대비되는 **궤적(단일 해) 기반 메타휴리스틱**.
작업 우선순위 순열을 해(state)로 두고, 이웃해(두 위치 교환)로 이동하며
온도(T)에 따라 더 나쁜 해도 확률적으로 수용해 지역 최적을 탈출한다.

공정 비교(consensus Principle 2):
  - 디코딩은 baseline/GA와 동일한 공유 디코더 greedy_resource_schedule
    (room + staff + turnover 제약 모두 동일) 사용.
  - 비용(목적)은 동일한 Σ wait(task). → baseline/RCPSP/GA와 같은 잣대.
  - random.Random(seed)로 재현 가능.
"""

from __future__ import annotations

import math
import random
import time
from typing import List, Optional

from backend.app.model import Instance, Schedule
from backend.app import graph as _graph
from backend.app.baseline import greedy_resource_schedule

DEFAULT_SEED: int = 42
DEFAULT_MAX_ITERS: int = 6000
DEFAULT_COOLING: float = 0.9975  # geometric cooling factor per iteration


def _cost(instance: Instance, order: List[str]) -> int:
    """Σ wait(task) of the schedule decoded from *order* (the SA objective)."""
    sched = greedy_resource_schedule(instance, order, algo="sa")
    return sched.total_wait(instance)


def schedule_sa(
    instance: Instance,
    seed: int = DEFAULT_SEED,
    time_limit_sec: Optional[float] = None,
    max_iters: int = DEFAULT_MAX_ITERS,
    cooling: float = DEFAULT_COOLING,
    t_end: float = 0.5,
) -> Schedule:
    """Run Simulated Annealing and return the best Schedule found.

    Parameters
    ----------
    instance: validated scheduling problem.
    seed: RNG seed for reproducibility.
    time_limit_sec: optional wall-clock budget (for fair comparison with RCPSP/GA).
    max_iters: iteration cap when no time limit is hit.
    cooling: geometric temperature decay per iteration.
    t_end: floor temperature.
    """
    t0 = time.perf_counter()
    instance.validate()

    rng = random.Random(seed)
    task_ids: List[str] = list(instance.tasks.keys())
    n = len(task_ids)

    # 초기해: 위상정렬 순서(실행 가능·합리적 시작점)
    current = _graph.topological_order(instance)
    # 누락 방지(위상정렬이 모든 작업을 포함하지만 방어적으로 보강)
    if len(current) != n:
        seen = set(current)
        current = current + [t for t in task_ids if t not in seen]

    current_cost = _cost(instance, current)
    best, best_cost = list(current), current_cost

    # 초기 온도: 비용 규모에 비례(수용 확률이 의미 있도록)
    temp = max(10.0, current_cost * 0.15)

    iters = 0
    while iters < max_iters:
        iters += 1
        if time_limit_sec is not None and (time.perf_counter() - t0) >= time_limit_sec:
            break
        if n >= 2:
            i, j = rng.randrange(n), rng.randrange(n)
            while j == i:
                j = rng.randrange(n)
            neighbor = list(current)
            neighbor[i], neighbor[j] = neighbor[j], neighbor[i]  # 이웃: 두 위치 교환
        else:
            neighbor = list(current)

        n_cost = _cost(instance, neighbor)
        delta = n_cost - current_cost
        # 더 좋으면 수용, 나쁘면 exp(-Δ/T) 확률로 수용
        if delta <= 0 or rng.random() < math.exp(-delta / max(temp, 1e-9)):
            current, current_cost = neighbor, n_cost
            if current_cost < best_cost:
                best, best_cost = list(current), current_cost

        temp = max(t_end, temp * cooling)

    sched = greedy_resource_schedule(instance, best, algo="sa")
    sched.wall_clock_sec = time.perf_counter() - t0
    sched.validate(instance)
    return sched
