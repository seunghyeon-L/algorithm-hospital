"""
ga.py — DEAP genetic algorithm for hospital surgery scheduling.

Encoding:
  An individual is a permutation of task indices (0..N-1), interpreted as
  the priority order in which tasks are dispatched to rooms.  A decoder
  converts a permutation into a valid Schedule by simulating greedy
  list-scheduling in that order while respecting precedence constraints:
  a task can only be dispatched once ALL its predecessors have been
  assigned (i.e. we skip tasks that are not yet ready and come back to
  them).  This guarantees every decoded individual is precedence-feasible.

Fitness:
  Σ wait(task)  —  IDENTICAL to metrics.py evaluate().total_wait (PINNED).
  Constraint violations (precedence or resource overflow) add a large
  penalty so that infeasible individuals are strongly disfavoured.
  In practice the decoder always produces feasible schedules, so the
  penalty is a safety net only.

Reproducibility:
  RNG seed is fixed via Python's `random` module (which DEAP uses
  internally) and via a local `random.Random` instance.  Same seed ⟹
  identical final schedule.

Wall-clock budget:
  `time_limit_sec` caps total GA wall-clock time, enabling a fair
  comparison with CP-SAT when both are given the same budget.
"""

from __future__ import annotations

import random
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
from deap import algorithms, base, creator, tools

from .model import Instance, Schedule, TaskAssignment
from .metrics import evaluate


# ---------------------------------------------------------------------------
# DEAP fitness / individual types (created once at module level)
# ---------------------------------------------------------------------------

# Guard against re-registration when the module is reloaded (e.g. in tests)
if not hasattr(creator, "FitnessMin"):
    creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
if not hasattr(creator, "Individual"):
    creator.create("Individual", list, fitness=creator.FitnessMin)


# ---------------------------------------------------------------------------
# Decoder: permutation → Schedule
# ---------------------------------------------------------------------------

def _decode(
    perm: List[int],
    task_ids: List[str],
    instance: Instance,
) -> Schedule:
    """Convert a permutation of task indices into a valid Schedule.

    The permutation defines a *priority order* list of task_id strings.
    Decoding is delegated entirely to the shared
    ``baseline.greedy_resource_schedule`` decoder, which enforces both
    precedence and resource (room + staff + turnover) constraints while
    placing tasks greedily in priority order.  This guarantees every
    decoded individual is feasible — no penalty is triggered in normal
    operation.

    Parameters
    ----------
    perm:
        A permutation of [0, 1, ..., N-1].
    task_ids:
        Ordered list of task_id strings so that task_ids[perm[i]] maps
        index → task_id.
    instance:
        The scheduling problem.

    Returns
    -------
    Schedule
        algo='ga', wall_clock_sec=0.0 (caller sets it).
    """
    from backend.app.baseline import greedy_resource_schedule

    # The permutation is a *priority order*.  Decode with the shared
    # resource-feasible greedy scheduler (respects rooms AND staff), identical
    # to baseline — so GA, baseline and RCPSP all solve the SAME constrained
    # problem (consensus Principle 2: fair comparison).
    priority_order = [task_ids[idx] for idx in perm]
    return greedy_resource_schedule(instance, priority_order, algo="ga")


# ---------------------------------------------------------------------------
# Fitness evaluation
# ---------------------------------------------------------------------------

_INFEASIBLE_PENALTY = 10 ** 9  # large penalty for unrecoverable failures


def _make_eval_fn(task_ids: List[str], instance: Instance):
    """Return a DEAP-compatible evaluation function for the given instance."""

    def evaluate_individual(individual: List[int]) -> Tuple[int]:
        try:
            sched = _decode(list(individual), task_ids, instance)
            # Use metrics.evaluate for PINNED Σwait — same formula as referee
            metrics = evaluate(sched, instance)
            return (metrics.total_wait,)
        except Exception:
            return (_INFEASIBLE_PENALTY,)

    return evaluate_individual


# ---------------------------------------------------------------------------
# Genetic operators
# ---------------------------------------------------------------------------

def _cx_ordered(ind1: List[int], ind2: List[int]) -> Tuple[List[int], List[int]]:
    """Ordered crossover (OX) for permutation individuals (in-place)."""
    tools.cxOrdered(ind1, ind2)
    return ind1, ind2


def _mut_shuffle(individual: List[int], indpb: float) -> Tuple[List[int]]:
    """Shuffle mutation: swap random pairs with probability indpb."""
    tools.mutShuffleIndexes(individual, indpb=indpb)
    return (individual,)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def schedule_ga(
    instance: Instance,
    seed: int = 42,
    pop_size: int = 100,
    n_gen: int = 200,
    cx_prob: float = 0.7,
    mut_prob: float = 0.2,
    mut_indpb: float = 0.05,
    time_limit_sec: Optional[float] = None,
    tournament_size: int = 3,
    hof_size: int = 1,
) -> Schedule:
    """Run a DEAP genetic algorithm and return the best Schedule found.

    Fitness = Σ wait(task) — identical to metrics.py evaluate().total_wait
    (PINNED objective).  Constraint-violation penalty is applied on decode
    failure only (safety net; decoder always produces feasible schedules for
    valid DAGs).

    Parameters
    ----------
    instance:
        The scheduling problem.  Must pass instance.validate().
    seed:
        Fixed RNG seed for full reproducibility.  Same seed ⟹ same schedule.
    pop_size:
        Number of individuals in the population.
    n_gen:
        Maximum number of generations.
    cx_prob:
        Crossover probability per pair.
    mut_prob:
        Mutation probability per individual.
    mut_indpb:
        Per-gene mutation probability inside shuffle mutation.
    time_limit_sec:
        Optional wall-clock budget in seconds.  GA stops early if this is
        exceeded (after completing the current generation).  Set to match
        CP-SAT time_limit for a fair comparison.
    tournament_size:
        Tournament selection size.
    hof_size:
        Hall-of-fame size (best individuals retained across generations).

    Returns
    -------
    Schedule
        algo='ga', wall_clock_sec set, valid per Schedule.validate().
    """
    instance.validate()
    t0 = time.perf_counter()

    # --- seed Python random (DEAP uses random internally) ---
    random.seed(seed)
    np.random.seed(seed)

    task_ids: List[str] = list(instance.tasks.keys())
    n = len(task_ids)

    # --- build DEAP toolbox ---
    toolbox = base.Toolbox()

    # Individual: random permutation of [0..N-1]
    rng = random.Random(seed)

    def _make_individual() -> creator.Individual:
        perm = list(range(n))
        rng.shuffle(perm)
        return creator.Individual(perm)

    toolbox.register("individual", _make_individual)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    eval_fn = _make_eval_fn(task_ids, instance)
    toolbox.register("evaluate", eval_fn)
    toolbox.register("mate", tools.cxOrdered)
    toolbox.register("mutate", tools.mutShuffleIndexes, indpb=mut_indpb)
    toolbox.register("select", tools.selTournament, tournsize=tournament_size)

    # --- initialise population ---
    pop = toolbox.population(n=pop_size)
    hof = tools.HallOfFame(hof_size)

    stats = tools.Statistics(lambda ind: ind.fitness.values[0] if ind.fitness.valid else float("inf"))
    stats.register("min", np.min)
    stats.register("avg", np.mean)

    # Evaluate initial population
    fitnesses = list(map(toolbox.evaluate, pop))
    for ind, fit in zip(pop, fitnesses):
        ind.fitness.values = fit

    hof.update(pop)

    # --- generational loop ---
    for gen in range(n_gen):
        # Check wall-clock budget
        if time_limit_sec is not None:
            elapsed = time.perf_counter() - t0
            if elapsed >= time_limit_sec:
                break

        # Selection
        offspring = toolbox.select(pop, len(pop))
        offspring = list(map(toolbox.clone, offspring))

        # Crossover
        for child1, child2 in zip(offspring[::2], offspring[1::2]):
            if rng.random() < cx_prob:
                toolbox.mate(child1, child2)
                del child1.fitness.values
                del child2.fitness.values

        # Mutation
        for mutant in offspring:
            if rng.random() < mut_prob:
                toolbox.mutate(mutant)
                del mutant.fitness.values

        # Evaluate offspring that were modified
        invalid = [ind for ind in offspring if not ind.fitness.valid]
        fitnesses = list(map(toolbox.evaluate, invalid))
        for ind, fit in zip(invalid, fitnesses):
            ind.fitness.values = fit

        # Replace population
        pop[:] = offspring
        hof.update(pop)

    elapsed = time.perf_counter() - t0

    # --- decode best individual ---
    best_perm = list(hof[0])
    best_sched = _decode(best_perm, task_ids, instance)
    best_sched.wall_clock_sec = elapsed

    # Validate before returning — fail fast
    best_sched.validate(instance)
    return best_sched
