"""
Tests for chat-to-report generation (Phase 1).

DONE conditions covered:
 (1) a mock conversation -> report that passes schema.py Pydantic validation
 (3) 3+ example conversations each produce reports with all required fields set
Also: grounding (no invented fields), API endpoint round-trip, and the saved
file lands in reports/ with the generator's naming convention.
"""

from __future__ import annotations

import importlib
import json

import pytest
from fastapi.testclient import TestClient

from app.chatbot.report_builder import (
    NoDiagnosisError,
    build_report_from_conversation,
)
from app.shared.schema import IncidentReport

HDR = {"X-Client-Id": "c2r-client"}


# ── mock conversations (diagnosed) ────────────────────────────────────────────


def _assistant_payload(incident_type, summary, steps, artifacts=None, matched=None):
    return {
        "answer": summary,
        "incident_summary": summary,
        "incident_type": incident_type,
        "confidence": 78,
        "low_confidence": False,
        "is_chat": False,
        "needs_clarification": False,
        "recommended_resolution": [
            {"step": i + 1, "title": s[:30], "action": s, "validation": "", "evidence": []}
            for i, s in enumerate(steps)
        ],
        "artifacts": artifacts or [],
        "supporting_sql": [],
        "matched_report_ids": matched or [],
        "retrieval": [{"incident_id": m, "title": f"{m} report", "source": None,
                       "filename": None, "open_url": None, "score": 0.9}
                      for m in (matched or [])],
        "raw": "{}",
    }


def _convo(symptom, incident_type, summary, steps, **kw):
    return [
        {"role": "user", "text": symptom, "has_image": False, "payload": None},
        {"role": "assistant", "text": summary,
         "payload": _assistant_payload(incident_type, summary, steps, **kw)},
    ]


EXAMPLE_CONVERSATIONS = [
    _convo(
        "our Kafka consumer lag keeps growing and consumers rebalance constantly",
        "Kafka consumer rebalance storm",
        "A slow handler exceeded max.poll.interval.ms causing constant rebalancing.",
        ["Reduce max.poll.records", "Move slow work off the poll thread",
         "Increase max.poll.interval.ms", "Redeploy and watch lag drain"],
        artifacts=[{"language": "bash", "title": "Check lag",
                    "content": "kafka-consumer-groups --describe --group g1"}],
        matched=["INC0012017"],
    ),
    _convo(
        "open /app/infra/docker-compose.yml: no such file or directory",
        "Missing configuration file",
        "The docker-compose.yml path is wrong; the file is not where the tool looked.",
        ["Locate the file with find", "Correct the path or scaffold the file",
         "Re-run docker compose config to validate"],
        artifacts=[{"language": "yaml", "title": "Scaffold",
                    "content": "services:\n  app:\n    image: myapp:latest"}],
    ),
    _convo(
        "TLS handshake failing between two internal services after hardening",
        "TLS version mismatch",
        "Service B now requires TLS 1.3 but Service A is pinned to TLS 1.2.",
        ["Capture the handshake_failure alert", "Enable TLS 1.3 on the client",
         "Roll out and confirm mTLS succeeds"],
        matched=["INC0012026"],
    ),
]


# ── (1) schema validation ─────────────────────────────────────────────────────


def test_built_report_passes_schema_validation():
    report, md = build_report_from_conversation(EXAMPLE_CONVERSATIONS[0])
    # Round-trip through Pydantic: dump -> re-validate -> zero errors.
    IncidentReport.model_validate(report.model_dump())
    assert isinstance(md, str) and md.startswith("# ")


# ── (3) 3+ conversations, all required metadata fields non-empty ──────────────


@pytest.mark.parametrize("convo", EXAMPLE_CONVERSATIONS)
def test_required_fields_non_empty(convo):
    report, _ = build_report_from_conversation(convo)
    m = report.metadata
    for field in ("incident_id", "title", "caller", "category", "date"):
        assert getattr(m, field).strip(), f"{field} must be non-empty"
    # subcategory is intentionally empty (not grounded) — allowed, not invented.
    # blocks must include the grounded content.
    types = [b.type for b in report.blocks]
    assert "heading" in types
    assert "paragraph" in types      # symptom / root cause
    assert "list" in types           # resolution steps


# ── grounding: nothing invented ───────────────────────────────────────────────


def test_report_is_grounded_in_conversation():
    convo = EXAMPLE_CONVERSATIONS[0]
    report, _ = build_report_from_conversation(convo)
    dumped = json.dumps(report.model_dump())
    # Symptom, incident type, a step, and the matched id all trace to the convo.
    assert "Kafka consumer rebalance storm" in dumped
    assert "max.poll.interval.ms" in dumped
    assert "INC0012017" in dumped
    # Title equals the diagnosed incident type (not fabricated).
    assert report.metadata.title == "Kafka consumer rebalance storm"


def test_undiagnosed_conversation_is_rejected():
    # A greeting-only / clarification conversation has nothing to report.
    greet = [
        {"role": "user", "text": "hello", "payload": None},
        {"role": "assistant", "text": "Hi!", "payload": {"incident_type": "Assistant",
         "is_chat": True, "needs_clarification": False}},
    ]
    with pytest.raises(NoDiagnosisError):
        build_report_from_conversation(greet)


# ── API round-trip + file naming ──────────────────────────────────────────────


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("CHAT_DB", str(tmp_path / "chat.db"))
    monkeypatch.setenv("DISABLE_CHATBOT", "1")
    import app.main as main
    importlib.reload(main)
    with TestClient(main.app) as c:
        yield c, tmp_path / "reports"


def _seed_conversation(store, client_id, convo) -> str:
    conv = store.create_conversation(client_id, "seeded")
    for m in convo:
        store.add_message(conv["id"], role=m["role"], text=m.get("text", ""),
                          payload=m.get("payload"))
    return conv["id"]


def test_endpoint_generates_and_saves_report(client):
    c, reports_dir = client
    store = c.app.state.chat_store
    conv_id = _seed_conversation(store, "c2r-client", EXAMPLE_CONVERSATIONS[1])

    res = c.post(f"/api/conversations/{conv_id}/report", headers=HDR)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    # generator naming convention: incident_<safe_id>_<timestamp>.json + .md pair
    fname = body["jsonFilename"]
    assert fname.startswith("incident_") and fname.endswith(".json")
    assert (reports_dir / fname).exists()
    assert (reports_dir / fname.replace(".json", ".md")).exists()
    # saved JSON re-validates against the schema.
    saved = json.loads((reports_dir / fname).read_text())
    IncidentReport.model_validate(saved)


def test_endpoint_rejects_undiagnosed(client):
    c, _ = client
    store = c.app.state.chat_store
    conv = store.create_conversation("c2r-client", "greet")
    store.add_message(conv["id"], role="user", text="hello")
    store.add_message(conv["id"], role="assistant", text="Hi!",
                      payload={"incident_type": "Assistant", "is_chat": True})
    res = c.post(f"/api/conversations/{conv['id']}/report", headers=HDR)
    assert res.status_code == 400


def test_endpoint_other_client_cannot_access(client):
    c, _ = client
    store = c.app.state.chat_store
    conv_id = _seed_conversation(store, "c2r-client", EXAMPLE_CONVERSATIONS[2])
    res = c.post(f"/api/conversations/{conv_id}/report",
                 headers={"X-Client-Id": "intruder"})
    assert res.status_code == 404
