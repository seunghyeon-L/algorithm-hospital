"""
scil.py — SCIL: SA-Seeded CP-SAT with Iterative LNS (hybrid, 5th algorithm).

Pattern from recent literature: a metaheuristic quickly produces a feasible
schedule, which warm-starts CP-SAT via AddHint; CP-SAT's parallel portfolio
(which includes LNS workers) then improves around that hint.  The same
feed-forward warm-start architecture was validated by the 3rd-place solution
of the 2024 Healthcare Timetabling Competition (arXiv:2511.04685).

Outer loop (k rounds): each round runs SA with a fresh seed (deterministic
restart diversification), then CP-SAT hinted with the incumbent (best schedule
seen so far).  The incumbent is only ever replaced by a strictly better
schedule, so SCIL is never worse (in Σwait) than any intermediate solution —
in particular never worse than its own first SA round.

Honest framing (PINNED for reporting): warm-starting guarantees a *floor*,
not an improvement over cold-start CP-SAT.  Compare SCIL vs CP-SAT on
"quality reached within the same wall-clock budget", not as "always better".

Objective: identical PINNED Σwait (model.py / metrics.py definitions).
Reproducibility: fixed seeds throughout; no wall-clock dependent decisions
other than the CP-SAT/SA time budgets themselves.
"""

from __future__ import annotations

import time
from typing import Optional

try:
    from .model import Instance, Schedule
    from .rcpsp import schedule_rcpsp
    from .sa import schedule_sa
except ImportError:  # pragma: no cover - script-style imports
    from backend.app.model import Instance, Schedule  # type: ignore[no-redef]
    from backend.app.rcpsp import schedule_rcpsp  # type: ignore[no-redef]
    from backend.app.sa import schedule_sa  # type: ignore[no-redef]

DEFAULT_TIME_LIMIT_SEC: float = 30.0
DEFAULT_RANDOM_SEED: int = 42
DEFAULT_OUTER_ROUNDS: int = 2
SA_BUDGET_FRACTION: float = 0.3  # share of each round spent on SA seeding


def schedule_scil(
    instance: Instance,
    time_limit_sec: float = DEFAULT_TIME_LIMIT_SEC,
    random_seed: int = DEFAULT_RANDOM_SEED,
    outer_rounds: int = DEFAULT_OUTER_ROUNDS,
) -> Schedule:
    """Run the SCIL hybrid and return the incumbent schedule (algo='scil').

    Round r (r = 0..k-1):
      1. SA with seed = random_seed + r and ~30% of the round budget.
      2. CP-SAT with the incumbent as warm-start hint and the remaining budget.
    The best Σwait schedule across all rounds is returned.

    Args:
        instance:       Validated Instance.
        time_limit_sec: Total wall-clock budget across all rounds.
        random_seed:    Base seed (SA rounds use random_seed + r).
        outer_rounds:   Number of SA->CP-SAT rounds (k >= 1).

    Returns:
        Schedule with algo='scil', valid per Schedule.validate().
    """
    if outer_rounds < 1:
        raise ValueError(f"outer_rounds must be >= 1, got {outer_rounds}")

    t0 = time.perf_counter()
    instance.validate()

    round_budget = time_limit_sec / outer_rounds
    sa_budget = round_budget * SA_BUDGET_FRACTION
    cp_budget = round_budget - sa_budget

    incumbent: Optional[Schedule] = None
    incumbent_wait: Optional[int] = None

    def _consider(candidate: Schedule) -> None:
        nonlocal incumbent, incumbent_wait
        wait = candidate.total_wait(instance)
        if incumbent_wait is None or wait < incumbent_wait:
            incumbent = candidate
            incumbent_wait = wait

    for r in range(outer_rounds):
        remaining = time_limit_sec - (time.perf_counter() - t0)
        if remaining <= 1.0 and incumbent is not None:
            break  # budget exhausted; keep incumbent

        # --- 1) SA seeding (restart diversification with fresh seed) -------
        sa_sched = schedule_sa(
            instance,
            seed=random_seed + r,
            time_limit_sec=min(sa_budget, max(0.5, remaining * 0.5)),
        )
        _consider(sa_sched)

        # --- 2) CP-SAT improvement around the incumbent hint ---------------
        remaining = time_limit_sec - (time.perf_counter() - t0)
        if remaining <= 0.5:
            break
        try:
            cp_sched = schedule_rcpsp(
                instance,
                time_limit_sec=min(cp_budget, remaining),
                random_seed=random_seed,
                hint_schedule=incumbent,
            )
            _consider(cp_sched)
        except ValueError:
            # CP-SAT found no feasible solution in its slice of the budget;
            # the SA incumbent still stands.
            pass

    assert incumbent is not None  # outer_rounds >= 1 guarantees one SA run

    elapsed = time.perf_counter() - t0
    result = Schedule(
        instance_id=instance.instance_id,
        algo="scil",
        assignments=incumbent.assignments,
        wall_clock_sec=elapsed,
    )
    result.validate(instance)
    return result
