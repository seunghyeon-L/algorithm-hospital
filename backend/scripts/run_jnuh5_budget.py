# -*- coding: utf-8 -*-
"""run_jnuh5_budget.py — time-budget × N sweep (native engine).

Shows how the result (and the CP-SAT wall / crossover point) moves as the time
limit changes, for SA / GA / HGA / CP-SAT, at a few N.

CLI:  --n 200,500,1000   --budgets 2,5,10,20,40,60   --seed 42   --weighted 0
"""
from __future__ import annotations
import argparse, csv, os

from backend.app.jnuh5 import generate_jnuh5_instance, patient_metrics
from backend.app.jnuh5_algos import baseline, cpsat
from backend.scripts.jnuh5_numba import sa_native, ga_native, hga_native


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", default="200,500,1000")
    ap.add_argument("--budgets", default="2,5,10,20,40,60")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--weighted", type=int, default=0)
    args = ap.parse_args()
    n_list = [int(x) for x in args.n.split(",")]
    budgets = [float(x) for x in args.budgets.split(",")]
    weighted = bool(args.weighted)
    key = "our_weighted_wait" if weighted else "our_total_wait"
    out = os.path.join(os.path.dirname(__file__), "_jnuh5_budget.csv")

    algos = [
        ("SA", lambda j, b: sa_native(j, weighted=weighted, budget=b, seed=1000 + args.seed)),
        ("GA", lambda j, b: ga_native(j, weighted=weighted, budget=b, seed=2500 + args.seed, seeded=False)),
        ("HGA", lambda j, b: hga_native(j, weighted=weighted, budget=b, seed=3000 + args.seed)),
        ("CP-SAT", lambda j, b: cpsat(j, weighted=weighted, time_limit=b, warm_order=list(j.instance.tasks.keys()))),
    ]
    names = [a for a, _ in algos]

    rows = []
    print(f"# budget x N sweep | objective={'weighted' if weighted else 'unweighted'} "
          f"| seed={args.seed}", flush=True)
    base_cache = {}
    for n in n_list:
        ji = generate_jnuh5_instance(n, args.seed)
        base_cache[n] = (ji, patient_metrics(ji, baseline(ji))[key])

    for n in n_list:
        ji, bval = base_cache[n]
        print(f"\n--- N={n} ({len(ji.instance.tasks)} tasks) | baseline {key}={bval:.0f} ---", flush=True)
        hdr = f"{'budget':>7}" + "".join(f"{nm:>12}" for nm in names) + "  (%vs baseline)"
        print(hdr, flush=True)
        for b in budgets:
            cells = []
            for nm, fn in algos:
                try:
                    s = fn(ji, b)
                    val = patient_metrics(ji, s)[key]
                    pct = 100.0 * (bval - val) / bval if bval else 0.0
                except Exception:
                    pct = float("nan")
                cells.append(pct)
                rows.append({"objective": "weighted" if weighted else "unweighted",
                             "N": n, "budget": b, "algo": nm, "pct_vs_baseline": round(pct, 2)})
            print(f"{b:7.0f}" + "".join(f"{c:11.1f}%" for c in cells), flush=True)
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
    print(f"\n# CSV -> {out}\n# done ({len(rows)} rows)", flush=True)


if __name__ == "__main__":
    main()
