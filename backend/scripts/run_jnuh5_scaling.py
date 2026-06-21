# -*- coding: utf-8 -*-
"""run_jnuh5_scaling.py — large-N scaling sweep using the NATIVE (numba) engine.

Shows where metaheuristics (native SA/GA/HGA) overtake CP-SAT as N grows — the
core 'our value-add' that the opponent (pure-Python, N=8-10) never reached.

Algorithms: baseline, SA(native), GA-seeded(native), HGA(native), CP-SAT.
Both objectives (unweighted / KTAS-weighted), normal scenario.

CLI:
  --n 100,200,300,500,700,1000   --budget 10.0   --seed 42
"""
from __future__ import annotations
import argparse, csv, os, time

from backend.app.jnuh5 import generate_jnuh5_instance, patient_metrics
from backend.app.jnuh5_algos import baseline, cpsat
from backend.scripts.jnuh5_numba import sa_native, ga_native, hga_native

OBJ = [("unweighted", False), ("weighted", True)]
PANEL = ["our_total_wait", "our_weighted_wait", "opp_total_wait", "opp_weighted_wait",
         "makespan", "or_utilization", "pacu_utilization", "n_tasks"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", default="100,200,300,500,700,1000")
    ap.add_argument("--budget", type=float, default=10.0)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    n_list = [int(x) for x in args.n.split(",")]
    out = os.path.join(os.path.dirname(__file__), "_jnuh5_scaling.csv")

    def run(name, ji, weighted, budget):
        if name == "baseline":
            return baseline(ji)
        if name == "SA":
            return sa_native(ji, weighted=weighted, budget=budget, seed=1000 + args.seed)
        if name == "GA-seeded":
            return ga_native(ji, weighted=weighted, budget=budget, seed=2500 + args.seed,
                             seeded=True, algo="GA-seeded")
        if name == "HGA":
            return hga_native(ji, weighted=weighted, budget=budget, seed=3000 + args.seed)
        if name == "CP-SAT":
            return cpsat(ji, weighted=weighted, time_limit=budget,
                         warm_order=list(ji.instance.tasks.keys()))
        raise ValueError(name)

    rows = []
    algos = ["baseline", "SA", "GA-seeded", "HGA", "CP-SAT"]
    print(f"# JNUH5 scaling | native engine | budget={args.budget}s seed={args.seed}", flush=True)
    for obj_name, weighted in OBJ:
        for n in n_list:
            ji = generate_jnuh5_instance(n, args.seed)
            key = "our_weighted_wait" if weighted else "our_total_wait"
            print(f"\n--- obj={obj_name} | N={n} ({len(ji.instance.tasks)} tasks) ---", flush=True)
            print(f"{'algo':12}{'our_wait':>13}{'opp_wait':>13}{'wgt_wait':>13}{'%base':>8}{'sec':>7}", flush=True)
            base_val = None
            for algo in algos:
                try:
                    s = run(algo, ji, weighted, args.budget)
                    m = patient_metrics(ji, s)
                except Exception as e:
                    print(f"{algo:12}  ERROR {type(e).__name__}: {e}", flush=True)
                    continue
                if algo == "baseline":
                    base_val = m[key]
                pct = 100.0 * (base_val - m[key]) / base_val if base_val else 0.0
                print(f"{algo:12}{m['our_total_wait']:13.0f}{m['opp_total_wait']:13.0f}"
                      f"{m['our_weighted_wait']:13.0f}{pct:7.1f}%{s.wall_clock_sec:7.1f}", flush=True)
                row = {"objective": obj_name, "N": n, "algo": algo,
                       "pct_vs_baseline": round(pct, 2), "runtime_sec": round(s.wall_clock_sec, 2)}
                row.update({k: round(m[k], 2) for k in PANEL})
                rows.append(row)
                with open(out, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                    w.writeheader(); w.writerows(rows)
    print(f"\n# CSV -> {out}\n# done ({len(rows)} rows)", flush=True)


if __name__ == "__main__":
    main()
