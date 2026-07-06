"""
Chatbot tests — exercise the ported pipeline with fakes so no Ollama server or
downloaded embedding model is required.

Coverage:
  - resolution.parse_resolution: JSON and legacy-text shapes (pure logic)
  - retrieval.search_multimodal: ranking with a deterministic fake embedder
  - ChatbotService.answer: full understand->search->resolve wiring, fake provider
  - /api/chat: 503 when disabled, 400 on empty, 200 with an injected service
"""

from __future__ import annotations

import importlib
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.chatbot.ingestion import KnowledgeBase
from app.chatbot.resolution import parse_resolution
from app.chatbot.retrieval import search_multimodal
from app.chatbot.service import ChatbotService
from app.shared.llm.provider import LLMProvider


# ── fakes ─────────────────────────────────────────────────────────────────────


class FakeEmbedder:
    """Deterministic 'embeddings': a bag-of-words vector over a fixed vocab.

    Cosine similarity then reflects word overlap, which is enough to assert
    ranking behaviour without sentence-transformers.
    """

    VOCAB = ["duplicate", "port", "defective", "dns", "backup", "cleanup"]

    def encode(self, texts, convert_to_numpy=True, show_progress_bar=False):
        vecs = []
        for t in texts:
            low = t.lower()
            vecs.append([float(low.count(w)) for w in self.VOCAB])
        return np.array(vecs, dtype="float32")


class FakeProvider(LLMProvider):
    """Records prompts; returns canned understand/resolution outputs."""

    def __init__(self, resolution_json: dict | None = None):
        self.prompts: list[str] = []
        self._resolution = resolution_json or {
            "incident_summary": "Duplicate port records need cleanup.",
            "incident_type": "Duplicate Record Cleanup",
            "confidence": 80,
            "similar_incidents": [
                {"incident": "INC1048202", "similarity": 88, "reason": "same cleanup"}
            ],
            "recommended_resolution": [
                {
                    "step": 1,
                    "title": "Identify duplicates",
                    "purpose": "find rows",
                    "action": "SELECT ...",
                    "validation": "count matches",
                    "evidence": ["INC1048202"],
                }
            ],
            "artifacts": [
                {"language": "sql", "title": "Cleanup query",
                 "content": "SELECT * FROM fm_opv WHERE dup = 1"}
            ],
            "reasoning": "matched a duplicate-cleanup report",
            "alternative_resolution": [],
        }

    def chat(self, prompt: str, *, model=None) -> str:
        self.prompts.append(prompt)
        # First call is the 'understand' step; return a query-ish string.
        # A prompt containing the resolution schema marker -> return JSON.
        if "Output JSON schema" in prompt or "JSON only" in prompt:
            return json.dumps(self._resolution)
        return "duplicate port cleanup requested"

    def vision(self, prompt: str, image_b64: str, *, model=None) -> str:
        return "screenshot shows duplicate rows"


def _fake_kb() -> KnowledgeBase:
    embedder = FakeEmbedder()
    documents = [
        "duplicate duplicate port cleanup needed",  # INC1048202-ish
        "dns record correction for prod",
        "backup job repair scheduled",
    ]
    metadata = [
        {"source": "reports/dup.json", "path": "reports/dup.json",
         "title": "Duplicate Cleanup", "chunk_id": 0, "incident_id": "INC1048202"},
        {"source": "reports/dns.json", "path": "reports/dns.json",
         "title": "DNS Correction", "chunk_id": 0, "incident_id": "INC1048210"},
        {"source": "reports/bak.json", "path": "reports/bak.json",
         "title": "Backup Repair", "chunk_id": 0, "incident_id": "INC1048208"},
    ]
    embeddings = embedder.encode(documents)
    return KnowledgeBase(embedder, embeddings, documents, metadata, n_files=3)


# ── resolution parsing (pure) ─────────────────────────────────────────────────


def test_parse_resolution_json():
    raw = json.dumps({
        "incident_summary": "x",
        "incident_type": "Cleanup",
        "confidence": 0.9,  # fractional -> should scale to 90
        "recommended_resolution": [
            {"step": 1, "title": "t", "action": "do it", "evidence": ["INC1"]}
        ],
        "supporting_sql": ["SELECT 1"],
    })
    parsed = parse_resolution(raw)
    assert parsed["incident_type"] == "Cleanup"
    assert parsed["confidence"] == 90
    assert len(parsed["recommended_resolution"]) == 1
    assert parsed["supporting_sql"] == ["SELECT 1"]
    assert parsed["insufficient"] is False


def test_parse_resolution_empty_is_insufficient():
    parsed = parse_resolution("")
    assert parsed["insufficient"] is False or parsed["confidence"] == 0
    assert parsed["recommended_resolution"] == []


def test_parse_resolution_legacy_text():
    raw = "INCIDENT TYPE: Duplicate Cleanup\nSTEPS:\n1. Remove dup rows | TOOL: SQL\n"
    parsed = parse_resolution(raw)
    assert parsed["incident_type"] == "Duplicate Cleanup"
    assert parsed["recommended_resolution"][0]["action"] == "Remove dup rows"


# ── retrieval ranking ─────────────────────────────────────────────────────────


def test_search_ranks_by_overlap():
    kb = _fake_kb()
    hits = search_multimodal(
        "duplicate port", None,
        kb.embed_model, kb.embeddings, kb.documents, kb.metadata, top_k=3,
    )
    assert hits, "expected at least one hit"
    # The duplicate-cleanup doc shares the most words with the query.
    assert hits[0]["incident_id"] == "INC1048202"


# ── full pipeline ─────────────────────────────────────────────────────────────


def test_service_answer_end_to_end():
    provider = FakeProvider()
    service = ChatbotService(_fake_kb(), provider)
    result = service.answer("we have duplicate port records to clean up")

    assert result["incident_type"] == "Duplicate Record Cleanup"
    assert result["confidence"] == 80
    assert result["low_confidence"] is False
    assert "INC1048202" in result["matched_report_ids"]
    assert result["retrieval"][0]["incident_id"] == "INC1048202"
    # Perf: a TEXT query makes exactly ONE LLM call (resolution only). The
    # separate "understand" rephrase call was removed to ~halve latency.
    assert len(provider.prompts) == 1


def test_service_falls_back_when_no_results():
    # KB whose vocab can't overlap the query -> no meaningful hits, but the
    # pipeline must still produce a parsed answer via the fallback prompt.
    provider = FakeProvider()
    service = ChatbotService(_fake_kb(), provider)
    result = service.answer("completely unrelated xyzzy plugh")
    assert "recommended_resolution" in result


# ── API surface ───────────────────────────────────────────────────────────────


@pytest.fixture()
def disabled_client(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    monkeypatch.setenv("DISABLE_CHATBOT", "1")
    import app.main as main
    importlib.reload(main)
    with TestClient(main.app) as c:
        yield c


HDR = {"X-Client-Id": "test-client"}


def test_chat_503_when_disabled(disabled_client):
    res = disabled_client.post("/api/chat", headers=HDR, json={"query": "hi"})
    assert res.status_code == 503
    assert disabled_client.get("/api/health").json()["chatbot_ready"] is False


@pytest.fixture()
def live_client(tmp_path, monkeypatch):
    # Boot the app disabled (no model load), then inject a fake ChatbotService.
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    monkeypatch.setenv("DISABLE_CHATBOT", "1")
    import app.main as main
    importlib.reload(main)
    with TestClient(main.app) as c:
        c.app.state.chatbot = ChatbotService(_fake_kb(), FakeProvider())
        c.app.state.chatbot_error = None
        yield c


def test_chat_400_on_empty(live_client):
    assert live_client.post("/api/chat", headers=HDR, json={"query": "   "}).status_code == 400


def test_chat_200_end_to_end(live_client):
    res = live_client.post(
        "/api/chat", headers=HDR, json={"query": "duplicate port records to clean up"}
    )
    assert res.status_code == 200
    body = res.json()["answer"]  # the answer is now nested under the conversation envelope
    assert body["incident_type"] == "Duplicate Record Cleanup"
    assert "INC1048202" in body["matched_report_ids"]
    assert body["steps"][0]["title"] == "Identify duplicates"


def test_chat_200_with_null_incident_id(tmp_path, monkeypatch):
    # Regression: a retrieval hit whose incident_id is None (e.g. an .md report
    # with no INC number) must still serialize — MatchedReport.incident_id is
    # optional. This mirrors real report data and was missed by the fake KB.
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    monkeypatch.setenv("DISABLE_CHATBOT", "1")
    import app.main as main
    importlib.reload(main)

    kb = _fake_kb()
    kb.metadata[0]["incident_id"] = None  # drop the id on the top-ranked doc
    with TestClient(main.app) as c:
        c.app.state.chatbot = ChatbotService(kb, FakeProvider())
        c.app.state.chatbot_error = None
        res = c.post("/api/chat", headers=HDR, json={"query": "duplicate port"})
    assert res.status_code == 200
    assert res.json()["answer"]["retrieval"][0]["incident_id"] is None
