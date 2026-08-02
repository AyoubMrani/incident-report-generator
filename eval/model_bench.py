#!/usr/bin/env python3
"""
eval/model_bench.py — compare candidate generation models on this corpus.

The model choice was previously justified by a comment ("llama3.2:3b measured
~2x faster than llama3:8b with equal-or-better answer quality"). That claim
predates the retrieval and grounding work, so it deserves re-measuring rather
than inheriting: cleaner context changes what a bigger model can do with it.

This drives the *pipeline*, not the raw model — same retrieval, same prompt,
same parsing and grounding rules — so the only variable is which model
generates. It runs in-process rather than over HTTP so it can swap models
without restarting the server, and it bypasses the answer cache for the same
reason.

Quality is scored on properties the answer must have to be useful, not on
wording:

    grounded_steps   at least 2 actionable steps
    cites_expected   the report we know documents this is the source
    has_artifact     at least one runnable snippet survived grounding
    no_contamination no command from an unrelated incident
    root_cause       a real root cause, not "not documented"

Usage:
    python eval/model_bench.py                        # 3b vs 8b
    python eval/model_bench.py --models llama3:8b     # one model
    python eval/model_bench.py --repeat 3             # stability check
    python eval/model_bench.py --json bench.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

DEFAULT_MODELS = ["llama3.2:3b", "llama3:8b"]

# query -> (fragment the cited report title must contain,
#           commands that would prove cross-incident contamination)
CASES = [
    (
        "how to rollback lineIds",
        "rollback",
        ["remove_duplicate_customers", "fm_opv"],
    ),
    (
        "how to remove duplicate customers",
        "",                       # several dedupe reports are legitimate
        ["menu.py"],
    ),
    (
        "intermittent dns resolution failures for internal services",
        "dns",
        ["menu.py", "remove_duplicate_customers"],
    ),
    (
        "kafka consumer group lag growing without bound",
        "",
        ["menu.py"],
    ),
    (
        "database connection pool exhausted",
        "",
        ["menu.py"],
    ),
]


def score(answer: dict, expect_title: str, forbidden: list[str]) -> dict:
    """Grade one answer on properties, not wording."""
    steps = answer.get("recommended_resolution") or []
    blob = json.dumps(answer).lower()
    titles = " ".join(
        f"{r.get('incident_id') or ''} {r.get('title') or ''}"
        for r in (answer.get("matched_reports") or [])
    ).lower()
    root = (answer.get("root_cause") or "").strip().lower()

    return {
        "grounded_steps": len(steps) >= 2,
        "cites_expected": (not expect_title) or (expect_title.lower() in titles),
        "has_artifact": any(
            (s.get("artifact") or {}).get("content", "").strip() for s in steps
        ),
        "no_contamination": not any(f.lower() in blob for f in forbidden),
        "root_cause": bool(root) and "not " not in root[:12],
        "confidence": answer.get("confidence") or 0,
        "n_steps": len(steps),
    }


def run_model(model: str, repeat: int) -> dict:
    from app.chatbot.service import ChatbotService
    from app.shared.llm.ollama_provider import OllamaProvider

    reports = str(Path(__file__).resolve().parents[1] / "reports")
    provider = OllamaProvider(text_model=model)
    service = ChatbotService.build(reports, provider)

    rows, latencies = [], []
    for query, expect, forbidden in CASES:
        for _ in range(repeat):
            # Bypass the answer cache: we are measuring generation, not the LRU.
            service.invalidate_cache()
            started = time.time()
            try:
                answer = service.answer(query)
            except Exception as exc:  # noqa: BLE001
                print(f"    {query[:38]:38s} ERROR: {exc}")
                rows.append({"query": query, "error": str(exc)})
                continue
            elapsed = time.time() - started
            latencies.append(elapsed)

            graded = score(answer, expect, forbidden)
            graded.update({"query": query, "seconds": round(elapsed, 1)})
            rows.append(graded)

            checks = [k for k in ("grounded_steps", "cites_expected", "has_artifact",
                                  "no_contamination", "root_cause") if graded[k]]
            print(f"    {query[:38]:38s} {graded['confidence']:3d}%  "
                  f"{graded['n_steps']}steps  {elapsed:5.1f}s  {len(checks)}/5")

    ok = [r for r in rows if "error" not in r]
    passed = sum(
        all(r[k] for k in ("grounded_steps", "cites_expected", "has_artifact",
                           "no_contamination", "root_cause"))
        for r in ok
    )
    return {
        "model": model,
        "rows": rows,
        "n": len(ok),
        "fully_passing": passed,
        "checks_passed": sum(
            sum(bool(r[k]) for k in ("grounded_steps", "cites_expected",
                                     "has_artifact", "no_contamination", "root_cause"))
            for r in ok
        ),
        "checks_total": len(ok) * 5,
        "mean_confidence": round(statistics.mean(
            [r["confidence"] for r in ok]) if ok else 0, 1),
        "mean_seconds": round(statistics.mean(latencies) if latencies else 0, 1),
        "median_seconds": round(statistics.median(latencies) if latencies else 0, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--json", dest="json_out", default="")
    args = parser.parse_args()

    results = []
    for model in args.models:
        print(f"\n=== {model} ===")
        results.append(run_model(model, args.repeat))

    print("\n" + "=" * 72)
    print(f"{'model':16s} {'quality':>12s} {'cases':>8s} {'conf':>7s} "
          f"{'median':>8s} {'mean':>7s}")
    print("-" * 72)
    for r in results:
        quality = f"{r['checks_passed']}/{r['checks_total']}"
        cases = f"{r['fully_passing']}/{r['n']}"
        print(f"{r['model']:16s} {quality:>12s} {cases:>8s} "
              f"{r['mean_confidence']:6.1f}% {r['median_seconds']:7.1f}s "
              f"{r['mean_seconds']:6.1f}s")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(results, indent=2))
        print(f"\nwritten to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
