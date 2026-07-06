"""Tests for BM25 lexical index, RRF fusion, and the feedback loop."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient
import importlib

from app.chatbot.bm25 import BM25Index, tokenize
from app.chatbot.retrieval import _rrf_fuse
from app.chatbot.service import ChatbotService
from tests.test_conversations import _fake_kb
from tests.test_chatbot import FakeProvider

HDR = {"X-Client-Id": "bf-client"}


# ── BM25 ──────────────────────────────────────────────────────────────────────


def test_tokenize_keeps_ids_and_underscores():
    toks = tokenize("INC0383919 support_remove_opv_duplicate D-status")
    assert "inc0383919" in toks
    assert "support_remove_opv_duplicate" in toks  # underscores kept whole
    assert "status" in toks


def test_bm25_ranks_exact_term_first():
    docs = [
        "generic cleanup of database rows",
        "incident INC0383919 defective port D status fm_opv",
        "dns record correction for production host",
    ]
    idx = BM25Index(docs)
    ranking = idx.rank("INC0383919")
    assert ranking and ranking[0] == 1  # the doc containing the exact id


def test_bm25_empty_query_scores_zero():
    idx = BM25Index(["some text here", "more text"])
    assert idx.rank("") == []


# ── RRF fusion ────────────────────────────────────────────────────────────────


def test_rrf_promotes_doc_ranked_high_by_both():
    # doc 2 is top by vectors and appears in BM25 -> should win the fusion.
    sem = np.array([0.1, 0.2, 0.9])
    bm25_ranking = [2, 0]
    fused = _rrf_fuse(sem, bm25_ranking)
    assert max(fused, key=fused.get) == 2


def test_rrf_lexical_only_hit_still_scored():
    # A doc vectors rank last but BM25 ranks first still gets meaningful weight.
    sem = np.array([0.9, 0.8, 0.05])
    fused = _rrf_fuse(sem, [2])
    # doc 2 got the top BM25 slot, so its fused score beats its vector-only rank.
    assert fused[2] > 1.0 / (60 + 2)


# ── feedback loop ─────────────────────────────────────────────────────────────


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("CHAT_DB", str(tmp_path / "chat.db"))
    monkeypatch.setenv("DISABLE_CHATBOT", "1")
    import app.main as main
    importlib.reload(main)
    with TestClient(main.app) as c:
        c.app.state.chatbot = ChatbotService(_fake_kb(), FakeProvider())
        c.app.state.chatbot_error = None
        yield c


def _assistant_msg_id(client):
    r = client.post("/api/chat", headers=HDR, json={"query": "duplicate port cleanup"}).json()
    return r["assistant_message_id"], r["conversation_id"]


def test_feedback_up_persists(client):
    mid, conv = _assistant_msg_id(client)
    assert client.post(f"/api/messages/{mid}/feedback", headers=HDR, json={"value": 1}).status_code == 200
    msgs = client.get(f"/api/conversations/{conv}/messages", headers=HDR).json()
    assert msgs[-1]["feedback"] == 1


def test_feedback_clear_and_summary(client):
    mid, _ = _assistant_msg_id(client)
    client.post(f"/api/messages/{mid}/feedback", headers=HDR, json={"value": -1})
    s = client.get("/api/feedback/summary").json()
    assert s["down"] == 1 and s["total_rated"] == 1
    # clear it
    client.post(f"/api/messages/{mid}/feedback", headers=HDR, json={"value": None})
    assert client.get("/api/feedback/summary").json()["total_rated"] == 0


def test_feedback_rejects_bad_value(client):
    mid, _ = _assistant_msg_id(client)
    assert client.post(f"/api/messages/{mid}/feedback", headers=HDR, json={"value": 5}).status_code == 400


def test_feedback_other_client_cannot_rate(client):
    mid, _ = _assistant_msg_id(client)
    r = client.post(f"/api/messages/{mid}/feedback", headers={"X-Client-Id": "intruder"}, json={"value": 1})
    assert r.status_code == 404


# ── typed artifacts (not SQL-only) ────────────────────────────────────────────


def test_parser_reads_typed_artifacts():
    import json
    from app.chatbot.resolution import parse_resolution
    raw = json.dumps({
        "incident_type": "Missing file",
        "confidence": 70,
        "recommended_resolution": [{"step": 1, "title": "t", "action": "a", "evidence": []}],
        "artifacts": [
            {"language": "bash", "title": "Locate file", "content": "find . -name docker-compose.yml"},
            {"language": "yaml", "title": "Fix", "content": "services:\n  app: {}"},
        ],
    })
    p = parse_resolution(raw)
    assert len(p["artifacts"]) == 2
    assert p["artifacts"][0]["language"] == "bash"
    assert "docker-compose.yml" in p["artifacts"][0]["content"]
    assert p["artifacts"][1]["language"] == "yaml"  # not SQL


def test_parser_backward_compat_supporting_sql_becomes_artifact():
    import json
    from app.chatbot.resolution import parse_resolution
    raw = json.dumps({
        "incident_type": "DB", "confidence": 60,
        "recommended_resolution": [{"step": 1, "title": "t", "action": "a"}],
        "supporting_sql": ["DELETE FROM x WHERE id=1"],
    })
    p = parse_resolution(raw)
    assert p["artifacts"] == [{"language": "sql", "title": "", "content": "DELETE FROM x WHERE id=1"}]
    assert p["supporting_sql"] == ["DELETE FROM x WHERE id=1"]  # legacy field preserved


# ── learned corrections influence the prompt ──────────────────────────────────


def test_corrections_injected_into_prompt():
    from app.chatbot.service import ChatbotService
    svc = ChatbotService(_fake_kb(), FakeProvider())
    prep = svc._prepare(
        "duplicate port cleanup", None, None,
        corrections=[{"question": "duplicate port cleanup",
                      "correction": "use support_remove_opv_duplicate, never a raw DELETE"}],
    )
    assert "LEARNED CORRECTIONS" in prep["prompt"]
    assert "support_remove_opv_duplicate" in prep["prompt"]


def test_correction_endpoint_and_relevance(client):
    r = client.post("/api/corrections", headers=HDR, json={
        "question": "docker-compose.yml not found error",
        "correction": "the file is missing; run 'find . -name docker-compose.yml' or create it",
    })
    assert r.status_code == 200
    store = client.app.state.chat_store
    rel = store.relevant_corrections("why do I get docker-compose.yml no such file")
    assert rel and "docker-compose" in rel[0]["question"]


def test_correction_requires_both_fields(client):
    assert client.post("/api/corrections", headers=HDR,
                       json={"question": "x", "correction": ""}).status_code == 400
