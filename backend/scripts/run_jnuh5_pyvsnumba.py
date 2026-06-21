# -*- coding: utf-8 -*-
"""run_jnuh5_pyvsnumba.py — same metaheuristics, Python decoder vs Numba decoder.

Demonstrates 'decoder starvation': with the pure-Python decoder the metaheuristic
gets far fewer evaluations in the same time budget, so it underperforms at large N.
The Numba decoder (bit-identical results) gives 10-40× more evaluations → much
better %improvement. This is exactly why the earlier teammate version (pure Python,
N=8-10) never reached the large-N regime.

CLI:  --n 200,500,1000   --budget 8.0   --seed 42
"""
from __future__ import annotations
import argparse, csv, os, time
import numpy as np

from backend.app.jnuh5 import (generate_jnuh5_instance, patient_metrics,
                               task_order, decode)
from backend.app.jnuh5_algos import baseline, ga as ga_py, hga as hga_py
from backend.scripts.jnuh5_numba import (extract_arrays_5, decode_obj,
                                         ga_native, hga_native)


def decode_speed(ji):
    """Return (python_ms, numba_ms) for one decode of the topological order."""
    arr = extract_arrays_5(ji)
    order = np.array([arr["idx"][t] for t in task_order(ji.instance)], np.int64)
    decode_obj(arr, order, False)  # warm JIT
    t = time.perf_counter()
    for _ in range(10):
        decode_obj(arr, order, False)
    nb = (time.perf_counter() - t) / 10 * 1000
    t = time.perf_counter()
    decode(ji.instance, task_order(ji.instance))
    py = (time.perf_counter() - t) * 1000
    return py, nb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", default="200,500,1000")
    ap.add_argument("--budget", type=float, default=8.0)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    n_list = [int(x) for x in args.n.split(",")]
    B = args.budget
    out = os.path.join(os.path.dirname(__file__), "_jnuh5_pyvsnumba.csv")

    rows = []
    print(f"# Python decoder vs Numba decoder | budget={B}s seed={args.seed}", flush=True)
    for n in n_list:
        ji = generate_jnuh5_instance(n, args.seed)
        bval = patient_metrics(ji, baseline(ji))["our_total_wait"]
        py_ms, nb_ms = decode_speed(ji)
        print(f"\n--- N={n} ({len(ji.instance.tasks)} tasks) | decode python={py_ms:.0f}ms "
              f"numba={nb_ms:.1f}ms (speedup {py_ms/nb_ms:.0f}x) ---", flush=True)
        print(f"   ~evals in {B:.0f}s:  python≈{B*1000/py_ms:.0f}   numba≈{B*1000/nb_ms:.0f}", flush=True)
        print(f"{'algo':14}{'Python %':>10}{'Numba %':>10}{'gap(pp)':>9}", flush=True)
        for name, pyfn, nbfn in [
            ("GA-seeded", lambda j: ga_py(j, weighted=False, budget=B, seed=2500 + args.seed, seeded=True),
             lambda j: ga_native(j, weighted=False, budget=B, seed=2500 + args.seed, seeded=True)),
            ("HGA", lambda j: hga_py(j, weighted=False, budget=B, seed=3000 + args.seed),
             lambda j: hga_native(j, weighted=False, budget=B, seed=3000 + args.seed)),
        ]:
            sp = patient_metrics(ji, pyfn(ji))["our_total_wait"]
            sn = patient_metrics(ji, nbfn(ji))["our_total_wait"]
            pp = 100.0 * (bval - sp) / bval if bval else 0.0
            pn = 100.0 * (bval - sn) / bval if bval else 0.0
            print(f"{name:14}{pp:9.1f}%{pn:9.1f}%{pn - pp:8.1f}", flush=True)
            rows.append({"N": n, "tasks": len(ji.instance.tasks), "algo": name,
                         "python_pct": round(pp, 2), "numba_pct": round(pn, 2),
                         "decode_python_ms": round(py_ms, 1), "decode_numba_ms": round(nb_ms, 2),
                         "speedup": round(py_ms / nb_ms, 1)})
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
    print(f"\n# CSV -> {out}\n# done ({len(rows)} rows)", flush=True)


if __name__ == "__main__":
    main()
