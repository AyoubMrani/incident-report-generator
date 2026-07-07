"""
eval/make_eval_set.py — build a labeled retrieval evaluation set.

For each report in reports/, we derive several questions with different query
styles, each labeled with the gold incident_id (the report it was derived from).
This lets the benchmark measure retrieval quality per query type.

HONEST CAVEAT (state this in the report): the questions are auto-generated from
the reports themselves, so they are *synthetic* — they test whether retrieval
can recover the source report from a paraphrase of its content, not real user
phrasing. This is a standard, reproducible proxy when no query logs exist; it is
a lower bound on difficulty (real queries are noisier). The eval set is written
to eval/eval_set.json for inspection and hand-editing.

Query styles per report:
  - title      : the report title as a question ("how to handle <title>?")
  - symptom    : first sentence of the root-cause paragraph (natural phrasing)
  - id         : the bare incident id (exact-match, BM25's strength)
  - keyword    : salient content tokens (table/function names, statuses)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPORTS = Path(__file__).resolve().parents[1] / "reports"
OUT = Path(__file__).resolve().parent / "eval_set.json"

_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "was", "were",
    "is", "are", "be", "by", "with", "that", "this", "after", "only", "had",
    "from", "into", "have", "has", "not", "but", "so", "as", "at", "it", "its",
}


def _load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("report", data)  # unwrap legacy shape


def _first_sentence(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    m = re.split(r"(?<=[.!?])\s", text)
    return m[0] if m else text


def _root_cause(report: dict) -> str:
    for b in report.get("blocks", []):
        if b.get("type") == "paragraph" and "cause" in (b.get("title") or "").lower():
            return _first_sentence(b.get("content", ""))
    # fallback: first paragraph
    for b in report.get("blocks", []):
        if b.get("type") == "paragraph":
            return _first_sentence(b.get("content", ""))
    return ""


def _salient_keywords(report: dict, k: int = 5) -> str:
    """Pick distinctive tokens: table/function names (with _), status codes, caps."""
    text = json.dumps(report)
    toks = re.findall(r"[a-zA-Z][a-zA-Z0-9_]{3,}", text)
    scored = {}
    for t in toks:
        tl = t.lower()
        if tl in _STOP:
            continue
        score = 0
        if "_" in t:            # function/table names
            score += 3
        if any(c.isupper() for c in t[1:]):  # CamelCase / codes
            score += 1
        if len(t) > 6:
            score += 1
        scored[t] = max(scored.get(t, 0), score)
    top = sorted(scored, key=lambda x: scored[x], reverse=True)[:k]
    return " ".join(top)


def build() -> list[dict]:
    queries: list[dict] = []
    for path in sorted(REPORTS.glob("*.json")):
        report = _load(path)
        meta = report.get("metadata", {})
        inc = meta.get("incident_id")
        title = meta.get("title")
        if not inc or not title:
            continue

        rc = _root_cause(report)
        kw = _salient_keywords(report)

        if title:
            queries.append({"query": f"how do I handle {title.lower()}?",
                            "gold": inc, "style": "title"})
        if rc and len(rc) > 20:
            queries.append({"query": rc, "gold": inc, "style": "symptom"})
        queries.append({"query": inc, "gold": inc, "style": "id"})
        if kw:
            queries.append({"query": kw, "gold": inc, "style": "keyword"})

    return queries


if __name__ == "__main__":
    qs = build()
    OUT.write_text(json.dumps(qs, indent=2), encoding="utf-8")
    by_style: dict[str, int] = {}
    golds = set()
    for q in qs:
        by_style[q["style"]] = by_style.get(q["style"], 0) + 1
        golds.add(q["gold"])
    print(f"wrote {len(qs)} queries over {len(golds)} reports -> {OUT}")
    print("by style:", by_style)
