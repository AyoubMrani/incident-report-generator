"""
chatbot/selection.py — Gate 3: source selection and relevance ranking.

Retrieval returns the top-K candidates, but topical similarity is not the same
as actually answering the question: a query about rolling back LineIDs and an
unrelated ETL-repair report can both score highly because both mention
"rollback". Feeding every candidate to the generator produces answers that mix
steps from the wrong report and cite sources that were never used.

This module narrows the candidates to the ones that genuinely match, BEFORE the
prompt is built:

  1. de-duplicate: the same underlying report can appear as several chunks (and
     as near-duplicate files); keep its best-scoring instance only
  2. score entity overlap between the query and each report's title/content —
     identifiers, procedure names, system names — not just embedding proximity
  3. keep at most MAX_SELECTED reports, and drop candidates that are clearly
     weaker than the best one (relative threshold)

Only the selected reports reach the prompt and the citation list.
"""

from __future__ import annotations

import re

# At most this many reports are used to answer and cited.
MAX_SELECTED = 2

# A candidate is discarded when its combined score falls below this fraction of
# the best candidate's. Keeps a single strong match from being padded out with
# markedly weaker ones, while still allowing a genuine second source.
RELATIVE_FLOOR = 0.85

# Minimum combined score for a report to be cited at all. Below this the corpus
# does not actually document the question, and citing the nearest thing is worse
# than admitting it: it lends a real incident's authority to a guess. Calibrated
# on this corpus — genuine incident questions score ~1.04, unrelated questions
# ("tune a guitar", "COBOL batch scheduler") peak at 0.29 — so 0.50 separates
# them with a wide margin on both sides. Re-check with eval/model_bench.py if
# the scoring weights change.
ABSOLUTE_FLOOR = 0.50

# Weight of the lexical entity-overlap signal relative to the retrieval score.
# Retrieval scores are RRF-based and compressed into a small range, so entity
# overlap is what actually separates "mentions rollback" from "is about this".
_ENTITY_WEIGHT = 1.0

# Per-net-thumb adjustment applied to a report that has produced rated answers,
# and the cap on its total effect. Deliberately small: feedback breaks ties
# between reports that already match, it does not decide whether something
# matches. The cap keeps a popular report from dominating an unrelated query
# no matter how many upvotes it collects.
_FEEDBACK_STEP = 0.05
_FEEDBACK_CAP = 0.15

_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "is", "are",
    "how", "do", "i", "my", "it", "with", "why", "what", "this", "that", "from",
    "can", "you", "me", "please", "need", "want", "get", "we", "our",
}


def _tokens(text: str) -> set[str]:
    """Content tokens, keeping identifiers and composite names whole."""
    return {
        t for t in re.findall(r"[a-z0-9_]+", (text or "").lower())
        if t not in _STOP and len(t) > 2
    }


def _entity_overlap(query_tokens: set[str], hit: dict) -> float:
    """Fraction of the query's content tokens present in this report.

    Title matches count double: a report whose *title* contains the query's
    entities is far more likely to be the procedure being asked about than one
    that merely mentions them somewhere in its body.
    """
    if not query_tokens:
        return 0.0
    title_tokens = _tokens(hit.get("title") or "")
    body_tokens = _tokens(hit.get("text") or "")
    title_hits = len(query_tokens & title_tokens)
    body_hits = len(query_tokens & body_tokens)
    return min(1.0, (2 * title_hits + body_hits) / (2 * len(query_tokens)))


def _report_key(hit: dict) -> str:
    """Identify the underlying report so duplicates collapse to one entry."""
    inc = (hit.get("incident_id") or "").strip()
    if inc:
        return f"inc:{inc.lower()}"
    title = (hit.get("title") or "").strip().lower()
    if title:
        return f"title:{title}"
    return f"src:{(hit.get('source') or '').lower()}"


def select_sources(
    query: str,
    hits: list[dict],
    max_selected: int = MAX_SELECTED,
    feedback_scores: dict[str, int] | None = None,
) -> list[dict]:
    """Return the reports that genuinely answer `query`, best first.

    Each returned hit carries a `selection_score` (retrieval + entity overlap)
    for transparency. An empty list means nothing matched well enough, which is
    the only case where the missing-resolution fallback applies.

    `feedback_scores` maps a lowercased incident id to its net thumbs. It
    re-ranks reports that already cleared the relevance floors; it is applied
    *after* ABSOLUTE_FLOOR precisely so that upvotes cannot manufacture
    groundedness for a report the corpus does not actually match. Passing None
    disables the signal entirely, which is what every existing caller and test
    gets by default.
    """
    if not hits:
        return []

    q_tokens = _tokens(query)

    # 1. De-duplicate to one entry per underlying report (best chunk wins).
    best_by_report: dict[str, dict] = {}
    for hit in hits:
        key = _report_key(hit)
        scored = dict(hit)
        scored["selection_score"] = (
            float(hit.get("score") or 0.0) + _ENTITY_WEIGHT * _entity_overlap(q_tokens, hit)
        )
        current = best_by_report.get(key)
        if current is None or scored["selection_score"] > current["selection_score"]:
            best_by_report[key] = scored

    ranked = sorted(
        best_by_report.values(), key=lambda h: h["selection_score"], reverse=True
    )

    # 2. Absolute floor: with only a relative test the best candidate always
    #    survives, however weak — so a question the corpus knows nothing about
    #    still came back "grounded" in whatever ranked first, and the answer
    #    cited an unrelated incident. Measured separation on this corpus is
    #    wide (genuine matches 1.04, off-topic questions <= 0.29), so a floor
    #    in between rejects the latter without touching the former.
    top_score = ranked[0]["selection_score"]
    if top_score < ABSOLUTE_FLOOR:
        return []

    # 3. Relative floor: drop candidates far weaker than the best match, so a
    #    single strong match is not padded with a weak second source.
    kept = [h for h in ranked if h["selection_score"] >= RELATIVE_FLOOR * top_score]

    # 4. Feedback re-rank among the survivors. Everything here already passed
    #    both floors on topical merit, so this only decides *which* good match
    #    leads — the case it is for is two reports covering the same symptom
    #    where one has repeatedly been marked useful and the other has not.
    if feedback_scores:
        for hit in kept:
            inc = (hit.get("incident_id") or "").strip().lower()
            net = feedback_scores.get(inc, 0) if inc else 0
            if not net:
                continue
            adjustment = max(-_FEEDBACK_CAP, min(_FEEDBACK_CAP, net * _FEEDBACK_STEP))
            hit["feedback_adjustment"] = adjustment
            hit["selection_score"] += adjustment
        kept.sort(key=lambda h: h["selection_score"], reverse=True)

    return kept[:max_selected]
