# JNUH 5-stage surgery scheduling — team initial-version-aligned comparison study

> Terminology: the **"initial version"** below refers to **our own team's (4조) first
> implementation** (`jejunuh_or_scheduling_project.py`, 1,473 lines, pure Python),
> written by a teammate — **not a competing/opponent team**. This study aligns that
> setup to an improved version and asks what we adopted, changed, and added.

A self-contained RCPSP study that **aligns our team's initial-version setup to the
improved one** and runs it through our **native (Numba) engine** with rigorous,
evidence-grounded parameters. Built on top of the existing `model.py` / `metrics.py`
/ `baseline.py` (decoder) — the shared model gained a backward-compatible
`release_time` field (default 0), so all 167 prior tests still pass (186 total with
the 19 new jnuh5 tests).

## What it models

Each patient is a **5-stage DAG** (identical to the initial version for apples-to-apples):

```
        PRECHECK ┐
                 ├─> SURG ─> REC ─> DISCHARGE
        PREP ────┘
```

- **PRECHECK** (수술 전 확인) and **PREP** (마취 준비) run in parallel, both feeding SURG.
- **Resources** (ours + recovery bed): `room=12 · staff/nurse=24 · anesthesia=8 ·
  pacu_bed=18 ·` per-department surgeons. Turnover (20 min) applies to `room` only.
- **24h continuous** operation (no operating-day / slot structure — a deliberate
  simplification; see analysis memo).

## Two objectives, two wait definitions

| | definition | role |
|---|---|---|
| **objective (unweighted)** | `Σ_task (start − ready)` | our PINNED Σwait |
| **objective (weighted)** | `Σ_task w·(start − ready)`, `w` = KTAS 16:8:4:2:1 | urgency-aware |
| **report — ours** | `Σ_task (start − ready)` | resource-contention, per-task |
| **report — initial version** | `Σ_patient (discharge_end − arrival − Σstage_dur)` | patient flow wait |

`ready = max(release_time, max predecessor end)`. Both wait definitions are
reported for every run so the comparison is direct.

## Parameter provenance (all evidence-grounded)

| parameter | value | basis |
|---|---|---|
| SURG duration | per-procedure lognormal | operative-time literature |
| PRECHECK | tri(5,10,15) min | 박말영 2009 (입실→마취전 3.7분) + PubMed components |
| PREP | tri(10,20,40) min | Yoon 2005 ACT 12–17min (대한마취과학회지); PMC10985884 |
| REC | 0.2·SURG + tri(30,50,90), clamp[35,180] | 박형숙 2012 PACU 36.7min; PMC10702030 (n=24k). Proportional coefficient/clamps = our design |
| DISCHARGE | tri(30,60,120) min | LHSC floor 30; PADSS; PMID 15875124 |
| turnover | 20 min | international benchmark; UZ Gent 30min |
| KTAS weights | 16:8:4:2:1 | KTAS *target times* (basis); time-inverse ×2 normalisation = our design (SWALIS/NCEPOD-consistent direction) |
| room=12 | HIRA registry (39100103) |

(Capacities `staff/anesthesia/pacu_bed` remain assumptions — handled by transparency
+ sensitivity analysis, as recorded in the `jnuh-arbitrary-values` memo.)

## Algorithms

`baseline` (topological greedy) · `SA` · `GA` · `GA-seeded` (6 heuristic seeds) ·
`HGA` (GA → hill-climb) · `CP-SAT` (interval model, release-aware, **warm-started**) ·
`SCIL` (SA → CP-SAT). All metaheuristics optimise a pluggable objective via the
shared Serial-SGS decoder and are **anytime** (never worse than baseline).

## Emergency scenarios

- **static** — emergency known a-priori (initial version's approach): solve once.
- **dynamic** — emergency arrives *unannounced* at t=120: plan electives → freeze
  started tasks → inject emergency → re-optimise the rest. (The initial version never
  did true dynamic re-scheduling — this is what we added.)

## Files

| file | role |
|---|---|
| `app/jnuh5.py` | generator · patient metadata · objective · full metric panel |
| `app/jnuh5_algos.py` | Python algorithms · emergency static/dynamic drivers |
| `scripts/jnuh5_numba.py` | native (Numba) multi-pred/multi-resource decoder + SA/GA/HGA |
| `scripts/run_jnuh5_experiment.py` | scenario × objective × N × algorithm sweep → CSV |
| `scripts/run_jnuh5_scaling.py` | large-N native scaling sweep → CSV |
| `scripts/run_jnuh5_budget.py` | time-budget × N sweep (SA/GA-seeded/HGA/CP-SAT) → CSV |
| `scripts/run_jnuh5_pyvsnumba.py` | pure-Python decoder vs Numba decoder (starvation demo) → CSV |
| `tests/test_jnuh5.py` | structure, decode, metrics, anytime, numba-equivalence, dynamic |

## Running

```bash
# main comparison (small/medium N, all scenarios, both objectives)
python -m backend.scripts.run_jnuh5_experiment --n 10,50,100,200 --budget 5.0

# large-N scaling with the native engine (where metaheuristics overtake CP-SAT)
python -m backend.scripts.run_jnuh5_scaling --n 100,200,300,500,700,1000 --budget 10.0

# time-budget sweep (how the CP-SAT wall / crossover moves with the time limit)
python -m backend.scripts.run_jnuh5_budget --n 200,500,1000 --budgets 2,5,10,20,40,60

# Numba vs pure-Python decoder (decoder-starvation demonstration)
python -m backend.scripts.run_jnuh5_pyvsnumba --n 200,500,1000 --budget 8

# tests
python -m pytest backend/tests/test_jnuh5.py -q
```

## Key result pattern

- **Tiny N (≤10)**: JNUH's capacity absorbs the load → ~0 wait, algorithms tie
  (honest: a big hospital handles a few patients trivially).
- **Medium N (50–200)**: CP-SAT and HGA/GA-seeded lead; CP-SAT **dominates the
  weighted objective** (concentrates on high-KTAS patients).
- **Large N (500–1000, native only)**: GA-seeded/HGA reach **~33–40 %** improvement
  while CP-SAT hits a **time-threshold wall** (5000-task model: 0 % until it crosses
  the threshold — ~20–40 s at N=1000 — then it recovers). The scaling regime the
  initial version (pure-Python, N=8–10) never reached.

Native decoder verified **bit-identical** to the Python decoder; **~13×** faster
(732 ms → 58 ms per decode at N=500; measured 12.6–13.0× across N=200/500/1000),
which directly buys ~13× more search per time budget.
