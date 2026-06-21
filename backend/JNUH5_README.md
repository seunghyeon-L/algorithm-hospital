# JNUH 5-stage surgery scheduling — opponent-aligned comparison study

A self-contained RCPSP study that **aligns the opponent team's setup to ours** and
runs it through our **native (Numba) engine** with rigorous, evidence-grounded
parameters. Built on top of the existing `model.py` / `metrics.py` / `baseline.py`
(decoder) — the shared model gained a backward-compatible `release_time` field
(default 0), so all 167 prior tests still pass.

## What it models

Each patient is a **5-stage DAG** (identical to the opponent for apples-to-apples):

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
| **report — opponent** | `Σ_patient (discharge_end − arrival − Σstage_dur)` | patient flow wait |

`ready = max(release_time, max predecessor end)`. Both wait definitions are
reported for every run so the comparison is direct.

## Parameter provenance (all evidence-grounded)

| parameter | value | basis |
|---|---|---|
| SURG duration | per-procedure lognormal | operative-time literature |
| PRECHECK | tri(5,10,15) min | 박말영 2009 (입실→마취전 3.7분) + PubMed components |
| PREP | tri(10,20,40) min | Yoon 2005 ACT 12–17min (대한마취과학회지); PMC10985884 |
| REC | 0.2·SURG + tri(30,50,90), clamp[35,180] | 박형숙 2012 PACU 36.7min; PMC10702030 (n=24k) |
| DISCHARGE | tri(30,60,120) min | LHSC floor 30; PADSS; PMID 15875124 |
| turnover | 20 min | international benchmark; UZ Gent 30min |
| KTAS weights | 16:8:4:2:1 | KTAS time-inverse (SWALIS/NCEPOD consistent) |
| room=12 | HIRA registry; crisis-8 = 2024 의정갈등 staffing cut |

(Capacities `staff/anesthesia/pacu_bed` remain assumptions — handled by transparency
+ sensitivity analysis, as recorded in the `jnuh-arbitrary-values` memo.)

## Algorithms

`baseline` (topological greedy) · `SA` · `GA` · `GA-seeded` (6 heuristic seeds) ·
`HGA` (GA → hill-climb) · `CP-SAT` (interval model, release-aware, **warm-started**) ·
`SCIL` (SA → CP-SAT). All metaheuristics optimise a pluggable objective via the
shared Serial-SGS decoder and are **anytime** (never worse than baseline).

## Emergency scenarios

- **static** — emergency known a-priori (opponent's approach): solve once.
- **dynamic** — emergency arrives *unannounced* at t=120: plan electives → freeze
  started tasks → inject emergency → re-optimise the rest. (The opponent never did
  true dynamic re-scheduling — this is our differentiator.)

## Files

| file | role |
|---|---|
| `app/jnuh5.py` | generator · patient metadata · objective · full metric panel |
| `app/jnuh5_algos.py` | Python algorithms · emergency static/dynamic drivers |
| `scripts/jnuh5_numba.py` | native (Numba) multi-pred/multi-resource decoder + SA/GA/HGA |
| `scripts/run_jnuh5_experiment.py` | scenario × objective × N × algorithm sweep → CSV |
| `scripts/run_jnuh5_scaling.py` | large-N native scaling sweep → CSV |
| `tests/test_jnuh5.py` | structure, decode, metrics, anytime, numba-equivalence, dynamic |

## Running

```bash
# main comparison (small/medium N, all scenarios, both objectives)
python -m backend.scripts.run_jnuh5_experiment --n 10,50,100,200 --budget 5.0

# large-N scaling with the native engine (where metaheuristics overtake CP-SAT)
python -m backend.scripts.run_jnuh5_scaling --n 100,200,300,500,700,1000 --budget 10.0

# correctness gate: numba decoder == python decoder (bit-identical Σwait)
python -m backend.scripts.jnuh5_numba

# tests
python -m pytest backend/tests/test_jnuh5.py -q
```

## Key result pattern

- **Tiny N (≤10)**: JNUH's capacity absorbs the load → ~0 wait, algorithms tie
  (honest: a big hospital handles a few patients trivially).
- **Medium N (50–200)**: CP-SAT and HGA/GA-seeded lead; CP-SAT **dominates the
  weighted objective** (concentrates on high-KTAS patients).
- **Large N (500–1000, native only)**: GA-seeded/HGA reach **~33 %** improvement
  where CP-SAT (5000-task model in seconds) hits its wall — the scaling regime the
  opponent (pure-Python, N=8–10) never reached.

Native decoder verified **bit-identical** to the Python decoder; **13×+** faster
(679 ms → 50 ms per decode at N=500, even under load).
