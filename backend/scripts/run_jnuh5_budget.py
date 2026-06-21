# -*- coding: utf-8 -*-
"""run_jnuh5_budget.py — time-budget × N sweep (native engine).

Shows how the result (and the CP-SAT wall / crossover point) moves as the time
limit changes, for the two protagonists GA-seeded and CP-SAT (+ HGA), at a few N.

CLI:  --n 200,500,1000   --budgets 2,5,10,20   --seed 42   --weighted 0
"""
from __future__ import annotations
import argparse, csv, os

from backend.app.jnuh5 import generate_jnuh5_instance, patient_metrics
from backend.app.jnuh5_algos import baseline, cpsat
from backend.scripts.jnuh5_numba import ga_native, hga_native


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", default="200,500,1000")
    ap.add_argument("--budgets", default="2,5,10,20")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--weighted", type=int, default=0)
    args = ap.parse_args()
    n_list = [int(x) for x in args.n.split(",")]
    budgets = [float(x) for x in args.budgets.split(",")]
    weighted = bool(args.weighted)
    key = "our_weighted_wait" if weighted else "our_total_wait"
    out = os.path.join(os.path.dirname(__file__), "_jnuh5_budget.csv")

    rows = []
    print(f"# budget x N sweep | objective={'weighted' if weighted else 'unweighted'} "
          f"| seed={args.seed}", flush=True)
    # cache baselines (budget-independent)
    base_cache = {}
    for n in n_list:
        ji = generate_jnuh5_instance(n, args.seed)
        base_cache[n] = (ji, patient_metrics(ji, baseline(ji))[key])

    for n in n_list:
        ji, bval = base_cache[n]
        print(f"\n--- N={n} ({len(ji.instance.tasks)} tasks) | baseline {key}={bval:.0f} ---", flush=True)
        print(f"{'budget':>8}{'GA-seeded':>12}{'HGA':>10}{'CP-SAT':>10}  (%vs baseline)", flush=True)
        for b in budgets:
            res = {}
            for name, fn in [("GA-seeded", lambda j: ga_native(j, weighted=weighted, budget=b, seed=2500 + args.seed, seeded=True)),
                             ("HGA", lambda j: hga_native(j, weighted=weighted, budget=b, seed=3000 + args.seed)),
                             ("CP-SAT", lambda j: cpsat(j, weighted=weighted, time_limit=b, warm_order=list(j.instance.tasks.keys())))]:
                try:
                    s = fn(ji)
                    val = patient_metrics(ji, s)[key]
                    pct = 100.0 * (bval - val) / bval if bval else 0.0
                except Exception as e:
                    pct = float("nan")
                res[name] = pct
                rows.append({"objective": "weighted" if weighted else "unweighted",
                             "N": n, "budget": b, "algo": name, "pct_vs_baseline": round(pct, 2)})
            print(f"{b:8.0f}{res['GA-seeded']:11.1f}%{res['HGA']:9.1f}%{res['CP-SAT']:9.1f}%", flush=True)
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
    print(f"\n# CSV -> {out}\n# done ({len(rows)} rows)", flush=True)


if __name__ == "__main__":
    main()
