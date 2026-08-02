#!/usr/bin/env python3
"""
eval/corpus_sweep.py — check every report in the corpus, not a chosen handful.

live_check.py covers hand-picked cases well, but a suite whose cases were
chosen by the person fixing the bugs can pass while the corpus at large is
broken. This sweeps *all* of it: for each report, ask a question derived from
that report's own title and assert the pipeline finds its way back.

Two modes, because they answer different questions and cost different amounts:

  retrieval  (default, seconds)  no LLM. For every report: does a question
             built from its title retrieve that report as the top source?
             This is where a silent regression in ingestion, chunking,
             scoring or the selection floor would show up first.

  answers    (--answers, ~30-40s per report) full pipeline including
             generation, scored on the same properties live_check uses.
             Sampled with --limit unless you want to sit through all of them.

Usage:
    python eval/corpus_sweep.py                  # retrieval over every report
    python eval/corpus_sweep.py --answers --limit 12
    python eval/corpus_sweep.py --json sweep.json

Exit status is non-zero if the pass rate falls below --min-pass (default 0.95),
so this is usable as a gate.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "is",
        "are", "was", "were", "after", "with", "by", "due", "from", "into"}


def query_from_title(title: str) -> str:
    """A plausible operator question derived from a report title.

    Deliberately not the title verbatim: stripping the incident id and the
    leading article makes it closer to how someone actually types, while
    keeping the entities that retrieval must key on.
    """
    text = re.sub(r"^INC\d+[_\-\s]*", "", title, flags=re.IGNORECASE)
    text = text.replace("_", " ").strip()
    words = [w for w in text.split() if w.lower() not in STOP]
    return " ".join(words) if len(words) >= 3 else text


def load_reports() -> list[dict]:
    """Every indexed report with a usable title, de-duplicated by source file."""
    from app.chatbot.ingestion import build_knowledge_base

    kb = build_knowledge_base(str(ROOT / "reports"))
    seen: dict[str, dict] = {}
    for meta in kb.metadata:
        source = meta["source"]
        if source in seen:
            continue
        title = (meta.get("title") or "").strip()
        # Skip reports whose title is only an id or a generated filename:
        # a query built from those tests nothing about retrieval.
        if not title or re.fullmatch(r"INC\d+", title, re.IGNORECASE):
            continue
        if title.lower().startswith("incident_untitled"):
            continue
        seen[source] = {"source": source, "title": title,
                        "incident_id": meta.get("incident_id")}
    return list(seen.values()), kb


def sweep_retrieval(reports: list[dict], kb) -> list[dict]:
    """For each report: does its own question retrieve it back?"""
    from app.chatbot.retrieval import search_multimodal
    from app.chatbot.selection import select_sources

    rows = []
    for report in reports:
        query = query_from_title(report["title"])
        hits = search_multimodal(
            query, None, kb.embed_model, kb.embeddings, kb.documents,
            kb.metadata, top_k=5, bm25=kb.bm25,
        )
        selected = select_sources(query, hits)
        top = selected[0]["source"] if selected else None
        rows.append({
            "title": report["title"],
            "query": query,
            "expected": report["source"],
            "got": top,
            "score": round(selected[0]["selection_score"], 3) if selected else 0.0,
            "n_selected": len(selected),
            "ok": top == report["source"],
        })
    return rows


def sweep_answers(reports: list[dict], limit: int, seed: int,
                  model: str = "") -> list[dict]:
    """Full pipeline on a sample, scored the way live_check scores."""
    from app.chatbot.service import ChatbotService
    from app.shared.llm.ollama_provider import OllamaProvider

    sample = reports[:]
    random.Random(seed).shuffle(sample)
    sample = sample[:limit]

    provider = OllamaProvider(text_model=model) if model else OllamaProvider()
    service = ChatbotService.build(str(ROOT / "reports"), provider)

    rows = []
    for report in sample:
        query = query_from_title(report["title"])
        service.invalidate_cache()
        started = time.time()
        try:
            answer = service.answer(query)
        except Exception as exc:  # noqa: BLE001
            rows.append({"title": report["title"], "ok": False,
                         "error": str(exc)})
            print(f"  ERROR {report['title'][:44]}: {exc}")
            continue

        steps = answer.get("recommended_resolution") or []
        cited = [r.get("source") for r in (answer.get("retrieval") or [])]
        confidence = answer.get("confidence") or 0
        checks = {
            "cited_itself": report["source"] in cited,
            "has_steps": len(steps) >= 1,
            "confident": confidence >= 60,
            # An answer must never be confident and empty at the same time.
            "coherent": not (confidence >= 70 and not steps),
        }
        row = {"title": report["title"], "query": query,
               "confidence": confidence, "n_steps": len(steps),
               "seconds": round(time.time() - started, 1),
               **checks, "ok": all(checks.values())}
        rows.append(row)
        mark = "ok  " if row["ok"] else "FAIL"
        print(f"  [{mark}] {report['title'][:46]:46s} {confidence:3d}% "
              f"{len(steps)}steps {row['seconds']:5.1f}s")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", action="store_true",
                        help="run full generation (slow) instead of retrieval only")
    parser.add_argument("--limit", type=int, default=12,
                        help="reports to sample in --answers mode")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--model", default="",
                        help="generation model to test in --answers mode "
                             "(default: whatever OLLAMA_MODEL resolves to)")
    parser.add_argument("--min-pass", type=float, default=0.95)
    parser.add_argument("--json", dest="json_out", default="")
    args = parser.parse_args()

    reports, kb = load_reports()
    print(f"corpus: {len(reports)} reports with usable titles\n")

    if args.answers:
        label = args.model or "default model"
        print(f"Full-pipeline sweep on {min(args.limit, len(reports))} "
              f"sampled reports ({label}):")
        rows = sweep_answers(reports, args.limit, args.seed, args.model)
    else:
        print("Retrieval sweep over every report:")
        rows = sweep_retrieval(reports, kb)
        for row in rows:
            if not row["ok"]:
                print(f"  [FAIL] {row['title'][:46]:46s} -> "
                      f"{(row['got'] or 'nothing selected')}")

    passed = sum(1 for r in rows if r.get("ok"))
    total = len(rows)
    rate = passed / total if total else 0.0
    print(f"\n{passed}/{total} passed ({rate:.1%})")

    if not args.answers and rows:
        scores = [r["score"] for r in rows if r["score"]]
        if scores:
            print(f"selection score: min {min(scores):.3f}  max {max(scores):.3f}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rows, indent=2))
        print(f"written to {args.json_out}")

    return 0 if rate >= args.min_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
