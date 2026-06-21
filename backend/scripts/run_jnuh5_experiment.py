# -*- coding: utf-8 -*-
"""run_jnuh5_experiment.py — full comparison runner for the 5-stage JNUH study.

Sweeps:  scenario × objective × N × algorithm.
Records the full metric panel (BOTH wait definitions: ours + opponent's).
Outputs a CSV and prints per-(scenario,objective) summary tables.

CLI (all optional):
  --n 10,50,100        patient-count sweep
  --budget 3.0         per-algorithm time budget (seconds)
  --seed 42
  --scenarios normal,emergency_static,emergency_dynamic
  --algos baseline,SA,GA,GA-seeded,HGA,CP-SAT,SCIL
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time

from backend.app.jnuh5 import generate_jnuh5_instance, patient_metrics
from backend.app.jnuh5_algos import (run_algorithm, solve_static_emergency,
                                     solve_dynamic_emergency)

ALL_ALGOS = ["baseline", "SA", "GA", "GA-seeded", "HGA", "CP-SAT", "SCIL"]
ALL_SCEN = ["normal", "emergency_static", "emergency_dynamic"]
OBJECTIVES = [("unweighted", False), ("weighted", True)]

PANEL = ["our_total_wait", "our_weighted_wait", "opp_total_wait", "opp_weighted_wait",
         "presurgery_wait", "avg_wait_per_patient", "max_patient_wait", "emergency_wait",
         "tardiness", "makespan", "overtime", "or_utilization", "anesthesia_utilization",
         "pacu_utilization", "staff_utilization", "n_patients", "n_tasks"]


def run_one(scenario, weighted, n, algo, budget, seed):
    """Run a single (scenario, objective, N, algo) cell -> (metrics, runtime, instance_for_metrics)."""
    if scenario == "emergency_dynamic":
        sched, ji = solve_dynamic_emergency(n, seed, algo, weighted=weighted, budget=budget)
        return patient_metrics(ji, sched), sched.wall_clock_sec
    inc_emerg = (scenario == "emergency_static")
    ji = generate_jnuh5_instance(n, seed, scenario=scenario, include_emergency=inc_emerg)
    sched = (solve_static_emergency(ji, algo, weighted=weighted, budget=budget, seed=seed)
             if inc_emerg else
             run_algorithm(algo, ji, weighted=weighted, budget=budget, seed=seed))
    return patient_metrics(ji, sched), sched.wall_clock_sec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", default="10,50,100")
    ap.add_argument("--budget", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--scenarios", default=",".join(ALL_SCEN))
    ap.add_argument("--algos", default=",".join(ALL_ALGOS))
    args = ap.parse_args()

    n_list = [int(x) for x in args.n.split(",")]
    scenarios = args.scenarios.split(",")
    algos = args.algos.split(",")
    out = os.path.join(os.path.dirname(__file__), "_jnuh5_results.csv")

    rows = []
    print(f"# JNUH 5-stage experiment | budget={args.budget}s seed={args.seed}", flush=True)
    print(f"# scenarios={scenarios} | objectives=unweighted,weighted | N={n_list}", flush=True)
    print(f"# algos={algos}\n", flush=True)

    for scenario in scenarios:
        for obj_name, weighted in OBJECTIVES:
            for n in n_list:
                # baseline first for %-improvement reference (key = our objective)
                key = "our_weighted_wait" if weighted else "our_total_wait"
                base_val = None
                print(f"--- scenario={scenario} | obj={obj_name} | N={n} ---", flush=True)
                hdr = f"{'algo':14}{'our_wait':>11}{'opp_wait':>11}{'wgt_wait':>11}{'emerg':>8}{'mksp':>7}{'%base':>8}{'sec':>7}"
                print(hdr, flush=True)
                for algo in algos:
                    t0 = time.perf_counter()
                    try:
                        m, rt = run_one(scenario, weighted, n, algo, args.budget, args.seed)
                    except Exception as e:
                        print(f"{algo:14}  ERROR {type(e).__name__}: {e}", flush=True)
                        continue
                    if algo == "baseline":
                        base_val = m[key]
                    pct = (100.0 * (base_val - m[key]) / base_val
                           if base_val not in (None, 0) else 0.0)
                    print(f"{algo:14}{m['our_total_wait']:11.0f}{m['opp_total_wait']:11.0f}"
                          f"{m['our_weighted_wait']:11.0f}{m['emergency_wait']:8.0f}"
                          f"{m['makespan']:7.0f}{pct:7.1f}%{rt:7.1f}", flush=True)
                    row = {"scenario": scenario, "objective": obj_name, "N": n,
                           "algo": algo, "pct_vs_baseline": round(pct, 2),
                           "runtime_sec": round(rt, 3)}
                    row.update({k: round(m[k], 2) for k in PANEL})
                    rows.append(row)
                    with open(out, "w", newline="", encoding="utf-8") as f:
                        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                        w.writeheader(); w.writerows(rows)
                print(flush=True)

    print(f"# CSV -> {out}\n# done ({len(rows)} rows)", flush=True)


if __name__ == "__main__":
    main()
