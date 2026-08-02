#!/usr/bin/env python3
"""
eval/compare_sweeps.py — put two corpus sweeps side by side, report by report.

Two separate summary tables invite the wrong comparison: a model can win on
mean confidence while losing on the questions that matter, and averages hide
which reports actually changed. Both sweeps are run with the same --seed, so
they cover the same reports in the same order and can be joined on title.

Usage:
    python eval/compare_sweeps.py sweep_3b.json sweep_8b.json \
        --labels llama3.2:3b llama3:8b
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

CHECKS = ("cited_itself", "has_steps", "confident", "coherent")


def load(path: str) -> dict[str, dict]:
    rows = json.loads(Path(path).read_text())
    return {r["title"]: r for r in rows if "error" not in r}


def summarise(rows: dict[str, dict]) -> dict:
    values = list(rows.values())
    if not values:
        return {}
    return {
        "n": len(values),
        "passed": sum(1 for r in values if r.get("ok")),
        "checks": sum(sum(bool(r.get(c)) for c in CHECKS) for r in values),
        "checks_total": len(values) * len(CHECKS),
        "confidence": statistics.mean(r["confidence"] for r in values),
        "steps": statistics.mean(r["n_steps"] for r in values),
        "median_s": statistics.median(r["seconds"] for r in values),
        "total_s": sum(r["seconds"] for r in values),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("first")
    parser.add_argument("second")
    parser.add_argument("--labels", nargs=2, default=["A", "B"])
    args = parser.parse_args()

    a, b = load(args.first), load(args.second)
    label_a, label_b = args.labels
    shared = [t for t in a if t in b]

    print(f"{len(shared)} reports covered by both sweeps\n")
    print(f"{'report':46s} {label_a:>14s} {label_b:>14s}")
    print("-" * 78)
    for title in shared:
        ra, rb = a[title], b[title]
        mark_a = "ok" if ra["ok"] else "FAIL"
        mark_b = "ok" if rb["ok"] else "FAIL"
        print(f"{title[:46]:46s} "
              f"{ra['confidence']:3d}% {ra['n_steps']}st {ra['seconds']:5.1f}s "
              f"{mark_b if False else ''}"
              f"{rb['confidence']:4d}% {rb['n_steps']}st {rb['seconds']:5.1f}s"
              f"{'' if ra['ok'] and rb['ok'] else f'   [{mark_a}/{mark_b}]'}")

    sa, sb = summarise({t: a[t] for t in shared}), summarise({t: b[t] for t in shared})
    print("\n" + "=" * 78)
    print(f"{'':22s} {label_a:>16s} {label_b:>16s}   verdict")
    print("-" * 78)

    def row(name: str, va, vb, fmt: str, higher_is_better: bool):
        if va == vb:
            verdict = "tie"
        elif (va > vb) == higher_is_better:
            verdict = label_a
        else:
            verdict = label_b
        print(f"{name:22s} {format(va, fmt):>16s} {format(vb, fmt):>16s}   {verdict}")

    row("reports passed", sa["passed"], sb["passed"], "d", True)
    row("property checks", sa["checks"], sb["checks"], "d", True)
    row("mean confidence", sa["confidence"], sb["confidence"], ".1f", True)
    row("mean steps", sa["steps"], sb["steps"], ".1f", True)
    row("median latency (s)", sa["median_s"], sb["median_s"], ".1f", False)
    row("total latency (s)", sa["total_s"], sb["total_s"], ".1f", False)

    # The decision rule, stated rather than left to the reader's eye: a slower
    # model has to actually answer more questions correctly to be worth it.
    print()
    if sb["passed"] > sa["passed"] or sb["checks"] > sa["checks"]:
        print(f"{label_b} answers more correctly — worth its latency cost.")
    elif sb["passed"] == sa["passed"] and sb["checks"] == sa["checks"]:
        faster = label_a if sa["median_s"] < sb["median_s"] else label_b
        print(f"Identical correctness ({sa['passed']}/{sa['n']} reports, "
              f"{sa['checks']}/{sa['checks_total']} checks). "
              f"{faster} is faster, so {faster} wins.")
    else:
        print(f"{label_a} answers more correctly and is not slower — "
              f"{label_a} wins outright.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
