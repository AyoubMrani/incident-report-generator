"""
tests/test_corpus_retrieval.py — every report must be findable, not just the
ones someone happened to write a test for.

The hand-picked cases in eval/live_check.py were chosen by whoever was fixing
the bugs, so they can all pass while the rest of the corpus quietly rots. This
sweeps the whole knowledge base: for each report, build a question from that
report's own title and assert the pipeline selects that report back.

No LLM involved, so it runs in CI at the speed of the embedding model. This is
the test that would have caught the duplicate .md/.json indexing and the title
regression on their own, without anyone noticing a bad answer by hand first.
"""

from __future__ import annotations

import re

import pytest

from app.chatbot.ingestion import build_knowledge_base
from app.chatbot.retrieval import search_multimodal
from app.chatbot.selection import ABSOLUTE_FLOOR, select_sources

REPORTS_DIR = "../reports"

_STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "is",
         "are", "was", "were", "after", "with", "by", "due", "from", "into"}


def _query_from_title(title: str) -> str:
    """A plausible operator question derived from a report title."""
    text = re.sub(r"^INC\d+[_\-\s]*", "", title, flags=re.IGNORECASE)
    text = text.replace("_", " ").strip()
    words = [w for w in text.split() if w.lower() not in _STOP]
    return " ".join(words) if len(words) >= 3 else text


@pytest.fixture(scope="module")
def kb():
    return build_knowledge_base(REPORTS_DIR)


@pytest.fixture(scope="module")
def reports(kb):
    """One entry per indexed report that has a real (non-id) title."""
    seen: dict[str, dict] = {}
    for meta in kb.metadata:
        source = meta["source"]
        if source in seen:
            continue
        title = (meta.get("title") or "").strip()
        if not title or re.fullmatch(r"INC\d+", title, re.IGNORECASE):
            continue
        if title.lower().startswith("incident_untitled"):
            continue
        seen[source] = {"source": source, "title": title}
    return list(seen.values())


def _select(kb, query: str):
    hits = search_multimodal(
        query, None, kb.embed_model, kb.embeddings, kb.documents, kb.metadata,
        top_k=5, bm25=kb.bm25,
    )
    return select_sources(query, hits)


def test_the_corpus_is_actually_indexed(reports):
    """A guard on the guard: an empty corpus would make every sweep vacuous."""
    assert len(reports) >= 50


def test_every_report_retrieves_itself(kb, reports):
    """The corpus-wide invariant: ask about a report, get that report.

    Reported as one failure listing every miss, because the useful signal is
    *which* reports became unreachable, not the first one alphabetically.
    """
    misses = []
    for report in reports:
        selected = _select(kb, _query_from_title(report["title"]))
        top = selected[0]["source"] if selected else None
        if top != report["source"]:
            misses.append(f"{report['title'][:50]} -> {top or 'nothing'}")

    assert not misses, (
        f"{len(misses)}/{len(reports)} reports did not retrieve themselves:\n  "
        + "\n  ".join(misses[:15])
    )


def test_every_genuine_match_clears_the_absolute_floor(kb, reports):
    """The floor rejects off-topic questions; it must not reject real ones.

    Without this, tightening ABSOLUTE_FLOOR later would silently start
    answering "nothing documented" for questions the corpus does document.
    """
    weak = []
    for report in reports:
        selected = _select(kb, _query_from_title(report["title"]))
        if not selected or selected[0]["selection_score"] < ABSOLUTE_FLOOR:
            score = selected[0]["selection_score"] if selected else 0.0
            weak.append(f"{report['title'][:50]} scored {score:.3f}")

    assert not weak, (
        f"{len(weak)} genuine matches fell below ABSOLUTE_FLOOR "
        f"({ABSOLUTE_FLOOR}):\n  " + "\n  ".join(weak[:10])
    )


def test_source_lists_stay_short(kb, reports):
    """Citing everything is not grounding. Gate 3 caps this at MAX_SELECTED."""
    from app.chatbot.selection import MAX_SELECTED

    for report in reports:
        selected = _select(kb, _query_from_title(report["title"]))
        assert len(selected) <= MAX_SELECTED, report["title"]


@pytest.mark.parametrize("query", [
    "how do I tune a guitar",
    "what is the best recipe for sourdough bread",
    "explain quantum entanglement",
    "how do I file my income taxes",
    "who won the world cup in 1998",
])
def test_off_topic_questions_select_nothing(kb, query):
    """The other half of the floor: unrelated questions must cite no report."""
    assert _select(kb, query) == []


def test_retrieval_is_deterministic(kb):
    """Two identical queries must select identically.

    Retrieval has no sampling, so any drift here would point at ordering that
    depends on dict iteration or unstable sorting — which would make every
    other assertion in this file flaky rather than false.
    """
    query = "kafka consumer group lag growing without bound"
    first = [h["source"] for h in _select(kb, query)]
    second = [h["source"] for h in _select(kb, query)]
    assert first == second and first
