"""Tests for rendering a chat answer as HTML with the report's screenshots."""

from __future__ import annotations

import importlib
import json

import pytest
from fastapi.testclient import TestClient

from app.chatbot.answer_html import extract_images, render_answer_html
from app.chatbot.service import ChatbotService
from tests.test_chatbot import FakeProvider
from tests.test_conversations import _fake_kb
from tests.test_stream_usecases import parse_sse

HDR = {"X-Client-Id": "html-client"}

_REPORT = {
    "metadata": {"incident_id": "INC900", "title": "Rollback", "caller": "x",
                 "category": "c", "subcategory": "s", "date": "2026-01-01"},
    "blocks": [
        {"id": "p1", "type": "paragraph", "title": "Steps",
         "content": '<p>Run the query.</p><img src="data:image/png;base64,AAA"/>'
                    '<p>Then the script.</p><img src="data:image/png;base64,BBB"/>'},
        {"id": "i1", "type": "image", "data_url": "data:image/png;base64,CCC",
         "caption": "final state"},
    ],
}

_ANSWER = {
    "answer": "Roll back the line IDs.",
    "incident_type": "Rollback",
    "confidence": 85,
    "low_confidence": False,
    "root_cause": "Root cause not explicitly documented in the source report.",
    "steps": [
        {"step": 1, "action_type": "SQL_QUERY", "title": "Extract",
         "action": "Run the query [SCREENSHOT 1]",
         "artifact": {"language": "sql", "title": "", "content": "SELECT 1;"},
         "evidence": ["INC900"]},
        {"step": 2, "action_type": "CODE", "title": "Run script",
         "action": "python menu.py",
         "artifact": {"language": "bash", "title": "", "content": "python menu.py"}},
    ],
    "retrieval": [{"incident_id": "INC900", "title": "Rollback", "filename": "r.json",
                   "source": None, "open_url": None, "score": 0.9}],
    "is_chat": False,
}


def test_extract_images_finds_inline_and_block_images():
    imgs = extract_images(_REPORT)
    assert len(imgs) == 3          # 2 inline in paragraph HTML + 1 image block
    assert any("AAA" in i for i in imgs) and any("CCC" in i for i in imgs)


def test_render_includes_sections_steps_and_code():
    html = render_answer_html(_ANSWER, _REPORT)
    assert "Problem Summary" in html and "Resolution Steps" in html
    assert "Data extraction (SQL)" in html and "Script / Terminal" in html
    assert 'class="language-sql"' in html and "SELECT 1;" in html
    assert "python menu.py" in html


def test_render_embeds_screenshots():
    html = render_answer_html(_ANSWER, _REPORT)
    assert html.count("<img") >= 3, "every screenshot from the report is embedded"
    assert "data:image/png;base64,AAA" in html


def test_render_escapes_untrusted_text():
    """Report-derived text must not inject markup into the rendered answer."""
    answer = dict(_ANSWER, answer='<script>alert(1)</script>')
    html = render_answer_html(answer, None)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_chat_reply_is_simple():
    html = render_answer_html({"is_chat": True, "answer": "Hello!"}, None)
    assert "Hello!" in html and "Resolution Steps" not in html


def test_render_marks_ai_suggestion_separately():
    answer = dict(_ANSWER, steps=[], no_documented_resolution=True,
                  ai_suggestion="Escalate to the owning team.")
    html = render_answer_html(answer, None)
    assert "AI-Suggested Recommendation (not a documented resolution)" in html
    assert "No documented resolution was found" in html


# ── endpoint ──────────────────────────────────────────────────────────────────


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


def test_message_html_endpoint(client):
    res = client.post("/api/chat/stream", headers=HDR, json={"query": "duplicate port cleanup"})
    done = [e for e in parse_sse(res.text) if e["type"] == "done"][0]
    mid = done["assistant_message_id"]

    html = client.get(f"/api/messages/{mid}/html", headers=HDR)
    assert html.status_code == 200
    assert "text/html" in html.headers["content-type"]
    assert "incident-response" in html.text


def test_message_html_requires_ownership(client):
    res = client.post("/api/chat/stream", headers=HDR, json={"query": "duplicate port cleanup"})
    mid = [e for e in parse_sse(res.text) if e["type"] == "done"][0]["assistant_message_id"]
    other = client.get(f"/api/messages/{mid}/html", headers={"X-Client-Id": "intruder"})
    assert other.status_code == 404
