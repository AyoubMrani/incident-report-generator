"""
tests/test_caching.py — answer cache, embedding cache, and KB refresh.

These three make the platform fast without letting it go stale, so the tests
focus on the staleness boundaries rather than the happy path: a cached answer
must never outlive the evidence it was built from, and a cached embedding must
never survive an edit to the text it encodes.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from app.chatbot import ingestion, service as service_module
from app.chatbot.service import ChatbotService


# ── fixtures ──────────────────────────────────────────────────────────────────


class _FakeProvider:
    """Counts calls so a cache hit is observable as 'the model never ran'."""

    def __init__(self, reply: str = "{}"):
        self.reply = reply
        self.calls = 0

    def chat(self, prompt: str) -> str:
        self.calls += 1
        return self.reply

    def chat_stream(self, prompt: str):
        self.calls += 1
        yield self.reply


def _svc() -> ChatbotService:
    return ChatbotService(object(), _FakeProvider())


def _good_answer() -> dict:
    return {
        "matched_reports": [{"title": "Rollback LineIDs"}],
        "recommended_resolution": [{"step": "run the rollback"}],
        "low_confidence": False,
    }


# ── answer cache ──────────────────────────────────────────────────────────────


def test_cache_returns_stored_answer_for_same_prompt():
    svc = _svc()
    svc._cache_put("PROMPT", _good_answer())
    assert svc._cache_get("PROMPT") == _good_answer()


def test_cache_misses_on_a_different_prompt():
    svc = _svc()
    svc._cache_put("PROMPT", _good_answer())
    assert svc._cache_get("OTHER PROMPT") is None


def test_cached_answer_is_isolated_from_caller_mutation():
    """Callers mutate answers (the store attaches ids); the cache must not see it."""
    svc = _svc()
    svc._cache_put("PROMPT", _good_answer())

    first = svc._cache_get("PROMPT")
    first["matched_reports"].append({"title": "INJECTED"})

    assert len(svc._cache_get("PROMPT")["matched_reports"]) == 1


@pytest.mark.parametrize(
    "answer",
    [
        {"matched_reports": [1], "recommended_resolution": [1], "low_confidence": True},
        {"matched_reports": [1], "recommended_resolution": [1],
         "no_documented_resolution": True},
        {"matched_reports": [], "recommended_resolution": [1]},
        {"matched_reports": [1], "recommended_resolution": []},
        {},
    ],
)
def test_weak_answers_are_never_cached(answer):
    """A bad answer must not be pinned for everyone who later asks the same thing."""
    svc = _svc()
    svc._cache_put("PROMPT", answer)
    assert svc._cache_get("PROMPT") is None


def test_cache_is_bounded_and_evicts_oldest_first(monkeypatch):
    monkeypatch.setattr(service_module, "ANSWER_CACHE_SIZE", 3)
    svc = _svc()
    for i in range(10):
        svc._cache_put(f"P{i}", _good_answer())

    assert len(svc._cache) == 3
    assert svc._cache_get("P9") is not None
    assert svc._cache_get("P0") is None


def test_cache_can_be_disabled(monkeypatch):
    monkeypatch.setattr(service_module, "ANSWER_CACHE_SIZE", 0)
    svc = _svc()
    svc._cache_put("PROMPT", _good_answer())
    assert svc._cache_get("PROMPT") is None


def test_invalidate_cache_clears_everything():
    svc = _svc()
    svc._cache_put("PROMPT", _good_answer())
    svc.invalidate_cache()
    assert svc._cache_get("PROMPT") is None


# ── embedding cache ───────────────────────────────────────────────────────────


def test_embedding_cache_key_changes_when_a_chunk_changes():
    base = ingestion._embedding_cache_key(["alpha", "beta"])
    assert base != ingestion._embedding_cache_key(["alpha", "beta modified"])
    assert base != ingestion._embedding_cache_key(["alpha"])
    assert base == ingestion._embedding_cache_key(["alpha", "beta"])


def test_embedding_cache_key_has_no_delimiter_collision():
    """['ab','c'] and ['a','bc'] are different corpora and must not share a key."""
    assert ingestion._embedding_cache_key(["ab", "c"]) != \
        ingestion._embedding_cache_key(["a", "bc"])


def test_embedding_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path))
    vectors = np.random.rand(4, 8).astype("float32")

    ingestion._store_cached_embeddings("key1", vectors)
    loaded = ingestion._load_cached_embeddings("key1", 4)

    assert loaded is not None
    assert np.allclose(loaded, vectors)


def test_embedding_cache_rejects_a_shape_mismatch(tmp_path, monkeypatch):
    """A cache file whose row count no longer matches the corpus is unusable."""
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path))
    ingestion._store_cached_embeddings("key1", np.random.rand(4, 8).astype("float32"))

    assert ingestion._load_cached_embeddings("key1", 99) is None


def test_embedding_cache_survives_a_corrupt_file(tmp_path, monkeypatch):
    """A truncated .npy must degrade to a re-encode, not crash startup."""
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path))
    (tmp_path / "key1.npy").write_bytes(b"not a numpy file")

    assert ingestion._load_cached_embeddings("key1", 4) is None


def test_embedding_cache_miss_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path))
    assert ingestion._load_cached_embeddings("never-written", 4) is None


def test_storing_a_new_key_evicts_the_previous_corpus(tmp_path, monkeypatch):
    """Only the current corpus is kept, so the cache dir can't grow forever."""
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path))
    ingestion._store_cached_embeddings("old", np.random.rand(2, 4).astype("float32"))
    ingestion._store_cached_embeddings("new", np.random.rand(2, 4).astype("float32"))

    assert {p.name for p in tmp_path.glob("*.npy")} == {"new.npy"}


# ── knowledge-base refresh ────────────────────────────────────────────────────


def _write_report(directory, incident_id: str, body: str) -> None:
    (directory / f"{incident_id}.json").write_text(
        json.dumps({
            "metadata": {"incident_id": incident_id, "title": body},
            "blocks": [{"type": "paragraph", "content": body}],
        }),
        encoding="utf-8",
    )


def test_refresh_is_a_noop_without_a_reports_dir():
    """Hand-built KBs (tests, fixtures) have no directory to re-index."""
    svc = _svc()
    assert svc.refresh() is False


def test_refresh_picks_up_a_newly_written_report(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path / "cache"))
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_report(reports, "INC001", "database connection pool exhausted")

    svc = ChatbotService.build(reports, _FakeProvider())
    before = len(svc.kb.documents)

    _write_report(reports, "INC002", "dns resolution failure on the edge router")
    assert svc.refresh() is True

    assert len(svc.kb.documents) > before
    assert any("dns resolution failure" in d.lower() for d in svc.kb.documents)


def test_refresh_drops_a_deleted_report_from_the_index(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path / "cache"))
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_report(reports, "INC001", "database connection pool exhausted")
    _write_report(reports, "INC002", "dns resolution failure on the edge router")

    svc = ChatbotService.build(reports, _FakeProvider())
    (reports / "INC002.json").unlink()
    svc.refresh()

    assert not any("dns resolution failure" in d.lower() for d in svc.kb.documents)


def test_refresh_invalidates_cached_answers(tmp_path, monkeypatch):
    """Answers shaped against the old corpus must not survive a re-index."""
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path / "cache"))
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_report(reports, "INC001", "database connection pool exhausted")

    svc = ChatbotService.build(reports, _FakeProvider())
    svc._cache_put("PROMPT", _good_answer())
    svc.refresh()

    assert svc._cache_get("PROMPT") is None


def test_failed_refresh_keeps_the_previous_index(tmp_path, monkeypatch):
    """Indexing an emptied directory raises; the working KB must stay in place."""
    monkeypatch.setenv("EMBED_CACHE_DIR", str(tmp_path / "cache"))
    reports = tmp_path / "reports"
    reports.mkdir()
    _write_report(reports, "INC001", "database connection pool exhausted")

    svc = ChatbotService.build(reports, _FakeProvider())
    original = svc.kb

    (reports / "INC001.json").unlink()  # build_knowledge_base now raises
    assert svc.refresh() is False
    assert svc.kb is original
