"""Tests for on-demand follow-up question suggestions."""

from __future__ import annotations

import importlib
import json

import pytest
from fastapi.testclient import TestClient

from app.chatbot.followups import (
    FollowupSuggester,
    _answer_summary,
    _clean_questions,
    parse_followups,
)
from app.chatbot.service import ChatbotService
from app.shared.llm.provider import LLMProvider
from tests.test_chatbot import FakeProvider
from tests.test_conversations import _fake_kb
from tests.test_stream_usecases import parse_sse

HDR = {"X-Client-Id": "followup-client"}


# ── parsing (pure) ──────────────────────────────────────────────────────────────


def test_parse_followups_clean_json():
    raw = json.dumps({"questions": ["What caused the timeout?", "How do I roll back?", "Is INC123 related?"]})
    assert parse_followups(raw) == [
        "What caused the timeout?",
        "How do I roll back?",
        "Is INC123 related?",
    ]


def test_parse_followups_accepts_fenced_json():
    raw = '```json\n{"questions": ["Why did it fail?", "Next step?"]}\n```'
    assert parse_followups(raw) == ["Why did it fail?", "Next step?"]


@pytest.mark.parametrize("raw", ["", "not json", "{}", '{"questions": "not a list"}'])
def test_parse_followups_never_raises_on_garbage(raw):
    assert parse_followups(raw) == []


def test_clean_questions_dedupes_case_insensitively():
    assert _clean_questions(["Why?", "why?", "WHY?", "What next?"]) == ["Why?", "What next?"]


def test_clean_questions_caps_at_three():
    out = _clean_questions([f"Question {i}?" for i in range(10)])
    assert len(out) == 3


def test_clean_questions_drops_overlong_entries():
    long_one = "This is a needlessly long follow up question that no one would actually type here?"
    out = _clean_questions([long_one, "Short one?"])
    assert long_one not in out
    assert "Short one?" in out


def test_clean_questions_adds_missing_question_mark():
    assert _clean_questions(["What about rollback"]) == ["What about rollback?"]


def test_clean_questions_ignores_non_strings():
    assert _clean_questions([1, None, {"q": "x"}, "Real question?"]) == ["Real question?"]


# ── answer summarisation (pure) ───────────────────────────────────────────────


def test_answer_summary_includes_key_fields():
    summary = _answer_summary({
        "incident_type": "Database",
        "incident_summary": "Disk full on primary.",
        "root_cause": "Log growth unbounded.",
        "recommended_resolution": [{"title": "Truncate logs"}, {"title": "Add alerting"}],
        "validation": "df -h shows headroom.",
    })
    assert "Database" in summary
    assert "Disk full on primary." in summary
    assert "Log growth unbounded." in summary
    assert "Truncate logs, Add alerting" in summary
    assert "df -h shows headroom." in summary


def test_answer_summary_handles_empty_answer():
    assert _answer_summary({}) == "(no structured answer available)"


def test_answer_summary_never_includes_raw_sql_artifact_content():
    """The summary must not smuggle a full runnable procedure into a
    differently-purposed prompt — only step titles are included."""
    answer = {
        "recommended_resolution": [
            {"title": "Cleanup", "artifact": {"content": "DROP TABLE customers;"}}
        ]
    }
    assert "DROP TABLE" not in _answer_summary(answer)


def test_answer_summary_is_bounded_in_length():
    huge = {"incident_summary": "x" * 5000}
    assert len(_answer_summary(huge)) < 1000


# ── FollowupSuggester (unit, fake provider) ──────────────────────────────────


class _RecordingProvider(LLMProvider):
    def __init__(self, response: str):
        self.response = response
        self.calls: list[str] = []

    def chat(self, prompt: str, *, model=None) -> str:
        self.calls.append(prompt)
        return self.response

    def chat_stream(self, prompt: str, *, model=None):
        yield self.response

    def vision(self, prompt: str, image_b64: str, *, model=None) -> str:
        return ""


def test_suggester_returns_parsed_questions():
    provider = _RecordingProvider(json.dumps({"questions": ["Next?", "Then?"]}))
    suggester = FollowupSuggester(provider)
    result = suggester.suggest("why did it fail", {"incident_summary": "x"})
    assert result == ["Next?", "Then?"]
    assert len(provider.calls) == 1


def test_suggester_caches_identical_question_and_answer():
    provider = _RecordingProvider(json.dumps({"questions": ["Q?"]}))
    suggester = FollowupSuggester(provider)
    suggester.suggest("same question", {"incident_summary": "same"})
    suggester.suggest("same question", {"incident_summary": "same"})
    assert len(provider.calls) == 1, "second call should be served from cache"


def test_suggester_does_not_cache_across_different_answers():
    provider = _RecordingProvider(json.dumps({"questions": ["Q?"]}))
    suggester = FollowupSuggester(provider)
    suggester.suggest("q", {"incident_summary": "first"})
    suggester.suggest("q", {"incident_summary": "second"})
    assert len(provider.calls) == 2


def test_suggester_degrades_to_empty_list_on_malformed_response():
    provider = _RecordingProvider("the model rambled instead of returning JSON")
    suggester = FollowupSuggester(provider)
    assert suggester.suggest("q", {}) == []


def test_suggester_prompt_does_not_leak_full_answer_verbatim():
    """The prompt sent to the model is the compressed summary, not the raw
    answer dict — this is what keeps the call cheap."""
    provider = _RecordingProvider(json.dumps({"questions": []}))
    suggester = FollowupSuggester(provider)
    big_answer = {"incident_summary": "s", "raw": "y" * 10_000}
    suggester.suggest("q", big_answer)
    assert len(provider.calls[0]) < 2000


# ── endpoint ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("CHAT_DB", str(tmp_path / "chat.db"))
    monkeypatch.setenv("DISABLE_CHATBOT", "1")
    import app.main as main
    importlib.reload(main)
    with TestClient(main.app) as c:
        provider = FakeProvider()
        c.app.state.chatbot = ChatbotService(_fake_kb(), provider)
        c.app.state.chatbot_error = None
        c.app.state.followups = FollowupSuggester(provider)
        yield c


def _ask_and_get_message_id(client) -> str:
    res = client.post("/api/chat/stream", headers=HDR, json={"query": "duplicate port cleanup"})
    done = [e for e in parse_sse(res.text) if e["type"] == "done"][0]
    return done["assistant_message_id"]


def test_followups_endpoint_returns_questions(client, monkeypatch):
    mid = _ask_and_get_message_id(client)

    # FakeProvider.chat always returns the canned resolution JSON regardless of
    # prompt content, which is not a valid {"questions": [...]} shape — swap in
    # a provider that speaks the follow-up schema for this call only.
    client.app.state.followups.provider = _RecordingProvider(
        json.dumps({"questions": ["What caused the duplicates?", "How to prevent recurrence?"]})
    )

    res = client.post(
        f"/api/messages/{mid}/followups",
        headers=HDR,
        json={"question": "duplicate port cleanup"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["questions"] == ["What caused the duplicates?", "How to prevent recurrence?"]


def test_followups_endpoint_requires_ownership(client):
    mid = _ask_and_get_message_id(client)
    res = client.post(
        f"/api/messages/{mid}/followups",
        headers={"X-Client-Id": "intruder"},
        json={"question": "x"},
    )
    assert res.status_code == 404


def test_followups_endpoint_404_for_unknown_message(client):
    res = client.post("/api/messages/does-not-exist/followups", headers=HDR, json={"question": "x"})
    assert res.status_code == 404


def test_followups_endpoint_503_when_chatbot_unavailable(client):
    mid = _ask_and_get_message_id(client)
    client.app.state.followups = None
    res = client.post(f"/api/messages/{mid}/followups", headers=HDR, json={"question": "x"})
    assert res.status_code == 503


def test_followups_endpoint_requires_auth_header(client):
    res = client.post("/api/messages/anything/followups", json={"question": "x"})
    assert res.status_code == 400


def test_followups_endpoint_empty_question_still_works(client):
    """A missing/empty question must not error — the answer summary alone is
    still enough context to propose something."""
    mid = _ask_and_get_message_id(client)
    client.app.state.followups.provider = _RecordingProvider(json.dumps({"questions": ["Q?"]}))
    res = client.post(f"/api/messages/{mid}/followups", headers=HDR, json={})
    assert res.status_code == 200
