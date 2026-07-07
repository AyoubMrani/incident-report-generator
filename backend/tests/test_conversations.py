"""
Tests for persistent conversations + source-link enrichment.

The ChatStore and conversation CRUD are tested with the chatbot disabled (no
model load). The /api/chat persistence path is tested by injecting a fake
ChatbotService so no Ollama is needed.
"""

from __future__ import annotations

import importlib

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.chatbot.ingestion import KnowledgeBase
from app.chatbot.service import ChatbotService, _source_link
from tests.test_chatbot import FakeEmbedder, FakeProvider  # reuse fakes


CID = "client-abc-123"
HDR = {"X-Client-Id": CID}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("CHAT_DB", str(tmp_path / "chat.db"))
    monkeypatch.setenv("DISABLE_CHATBOT", "1")
    import app.main as main
    importlib.reload(main)
    with TestClient(main.app) as c:
        yield c


def _fake_kb() -> KnowledgeBase:
    embedder = FakeEmbedder()
    docs = ["duplicate duplicate port cleanup"]
    meta = [{"source": "reports/INC1048202_dup.json", "path": "x",
             "title": "Duplicate Cleanup", "chunk_id": 0, "incident_id": "INC1048202"}]
    return KnowledgeBase(embedder, embedder.encode(docs), docs, meta, n_files=1)


# ── source link enrichment ────────────────────────────────────────────────────


def test_source_link_json_is_openable():
    link = _source_link({"source": "reports/INC1048202_dup.json", "incident_id": "INC1048202",
                         "title": "Duplicate Cleanup", "score": 0.9})
    assert link["filename"] == "INC1048202_dup.json"
    assert link["open_url"] == "/api/reports/content/INC1048202_dup.json"


def test_source_link_md_not_openable():
    link = _source_link({"source": "reports/notes.md", "incident_id": None,
                         "title": "notes", "score": 0.5})
    assert link["open_url"] is None


# ── conversation CRUD ─────────────────────────────────────────────────────────


def test_client_id_required(client):
    assert client.get("/api/conversations").status_code == 400


def test_conversations_start_empty(client):
    assert client.get("/api/conversations", headers=HDR).json() == []


def test_conversation_isolation_by_client(client):
    # Two clients: chat persists per client, never leaks across.
    inject_fake(client)
    client.post("/api/chat", headers=HDR, json={"query": "duplicate port"})
    other = client.get("/api/conversations", headers={"X-Client-Id": "someone-else"}).json()
    assert other == []
    mine = client.get("/api/conversations", headers=HDR).json()
    assert len(mine) == 1


def test_rename_and_delete(client):
    inject_fake(client)
    conv_id = client.post("/api/chat", headers=HDR, json={"query": "hello"}).json()["conversation_id"]
    assert client.patch(f"/api/conversations/{conv_id}", headers=HDR, json={"title": "Renamed"}).status_code == 200
    assert client.get("/api/conversations", headers=HDR).json()[0]["title"] == "Renamed"
    assert client.delete(f"/api/conversations/{conv_id}", headers=HDR).status_code == 200
    assert client.get("/api/conversations", headers=HDR).json() == []


# ── persistence across "reload" ───────────────────────────────────────────────


def inject_fake(client):
    """Attach a fake ChatbotService so /api/chat works without Ollama."""
    client.app.state.chatbot = ChatbotService(_fake_kb(), FakeProvider())
    client.app.state.chatbot_error = None


def test_chat_persists_and_replays(client):
    inject_fake(client)
    # Turn 1 (new conversation).
    r1 = client.post("/api/chat", headers=HDR, json={"query": "duplicate port cleanup"}).json()
    conv_id = r1["conversation_id"]
    # Turn 2 (same conversation).
    client.post("/api/chat", headers=HDR, json={"query": "any SQL?", "conversation_id": conv_id})

    # Replay: messages persisted in order (user, assistant, user, assistant).
    msgs = client.get(f"/api/conversations/{conv_id}/messages", headers=HDR).json()
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    # Assistant message carries the full structured answer for re-render.
    assert msgs[1]["payload"]["incident_type"] == "Duplicate Record Cleanup"
    assert msgs[1]["payload"]["retrieval"][0]["open_url"].endswith(".json")


def test_image_only_and_flags_persisted(client):
    inject_fake(client)
    # Image-only turn (no text) — must be accepted and marked has_image.
    r = client.post("/api/chat", headers=HDR, json={"query": "", "image_b64": "ZmFrZQ=="}).json()
    msgs = client.get(f"/api/conversations/{r['conversation_id']}/messages", headers=HDR).json()
    assert msgs[0]["role"] == "user" and msgs[0]["has_image"] is True


def test_links_attached_to_user_message(client):
    inject_fake(client)
    r = client.post("/api/chat", headers=HDR, json={
        "query": "see ticket", "links": ["https://tickets.example/INC1"]}).json()
    msgs = client.get(f"/api/conversations/{r['conversation_id']}/messages", headers=HDR).json()
    assert msgs[0]["payload"]["links"] == ["https://tickets.example/INC1"]


def test_cannot_post_to_others_conversation(client):
    inject_fake(client)
    conv_id = client.post("/api/chat", headers=HDR, json={"query": "hi"}).json()["conversation_id"]
    # A different client referencing that conversation id is rejected.
    r = client.post("/api/chat", headers={"X-Client-Id": "intruder"},
                    json={"query": "hi", "conversation_id": conv_id})
    assert r.status_code == 404
