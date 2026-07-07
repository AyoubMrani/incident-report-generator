"""
eval/error_analysis.py — where does hybrid retrieval fail, and why?

For every query the shipped (hybrid) retriever gets wrong (gold not in top-5),
we record the query, its style, the gold report, and what was retrieved instead.
We then summarize failures by query style and by a coarse cause tag, so the
report can characterize failure modes rather than only reporting aggregate wins.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.chatbot.ingestion import build_knowledge_base  # noqa: E402
import benchmark_retrieval as bench  # noqa: E402

EVAL = Path(__file__).resolve().parent / "eval_set.json"


def _cause(query: str, style: str) -> str:
    """Coarse cause tag for a miss (heuristic, for grouping in the report)."""
    if style == "id":
        return "exact-id not matched"
    if style == "keyword":
        return "keyword ambiguity (terms shared across reports)"
    if style == "symptom":
        return "paraphrase gap (wording differs from report)"
    return "title mismatch"


def run() -> dict:
    kb = build_knowledge_base(str(ROOT / "reports"))
    queries = json.loads(EVAL.read_text())

    failures = []
    for q in queries:
        ranked = bench._retrieve("hybrid", q["query"], kb)
        if q["gold"] not in ranked[:5]:
            failures.append({
                "query": q["query"],
                "style": q["style"],
                "gold": q["gold"],
                "retrieved": ranked[:3],
                "cause": _cause(q["query"], q["style"]),
            })

    by_style = Counter(f["style"] for f in failures)
    by_cause = Counter(f["cause"] for f in failures)
    return {
        "n_queries": len(queries),
        "n_failures": len(failures),
        "failure_rate": len(failures) / len(queries),
        "by_style": dict(by_style),
        "by_cause": dict(by_cause),
        "examples": failures,
    }


if __name__ == "__main__":
    r = run()
    print(f"Hybrid failures: {r['n_failures']}/{r['n_queries']} "
          f"({r['failure_rate']:.1%})\n")
    print("By query style:", r["by_style"])
    print("By cause:", r["by_cause"])
    print("\nFailure examples:")
    for f in r["examples"][:10]:
        print(f"  [{f['style']}] gold={f['gold']}  got={f['retrieved']}")
        print(f"     q: {f['query'][:70]!r}  ({f['cause']})")
