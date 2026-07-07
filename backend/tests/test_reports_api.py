"""
Smoke tests for the reports API — proves the server.ts port behaves the same.

Covers the behaviours that carried real logic in the original Express handler:
create, duplicate rejection (409), list ordering, content fetch, update, HTML
export, and delete. Uses an isolated temp reports dir per test via REPORTS_DIR.
"""

from __future__ import annotations

import importlib
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Point the app at an isolated reports dir, then (re)build the app so its
    # lifespan constructs ReportService against that dir. Disable the chatbot so
    # these tests don't load the embedding model.
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    monkeypatch.setenv("DISABLE_CHATBOT", "1")
    import app.main as main

    importlib.reload(main)
    with TestClient(main.app) as c:
        yield c


def _report(incident_id="INC001", title="Test"):
    return {
        "report": {
            "metadata": {
                "incident_id": incident_id,
                "title": title,
                "caller": "Ada",
                "category": "Network",
                "subcategory": "Cleanup",
                "date": "2026-07-03",
            },
            "blocks": [
                {"id": "b1", "type": "heading", "level": 1, "content": title},
                {
                    "id": "b2",
                    "type": "list",
                    "ordered": True,
                    "items": ["step one", "step two"],
                },
            ],
        },
        "markdown": f"# {title}\n\n- step one\n- step two\n",
    }


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["chatbot_ready"] is False  # disabled in this fixture


def test_create_and_list(client):
    res = client.post("/api/reports", json=_report())
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True and body["isUpdating"] is False
    assert body["jsonFilename"].startswith("incident_inc001_")

    listing = client.get("/api/reports").json()["reports"]
    assert len(listing) == 1
    assert listing[0]["metadata"]["incident_id"] == "INC001"


def test_duplicate_returns_409(client):
    assert client.post("/api/reports", json=_report()).status_code == 200
    dup = client.post("/api/reports", json=_report())
    assert dup.status_code == 409
    assert dup.json()["incident_id"] == "INC001"


def test_content_fetch_and_404(client):
    created = client.post("/api/reports", json=_report()).json()
    fetched = client.get(f"/api/reports/content/{created['jsonFilename']}")
    assert fetched.status_code == 200
    assert fetched.json()["metadata"]["title"] == "Test"

    assert client.get("/api/reports/content/nope.json").status_code == 404


def test_update_keeps_filename(client):
    created = client.post("/api/reports", json=_report()).json()
    payload = _report(title="Updated")
    payload["editingFilename"] = created["jsonFilename"]

    updated = client.post("/api/reports", json=payload).json()
    assert updated["isUpdating"] is True
    assert updated["jsonFilename"] == created["jsonFilename"]

    listing = client.get("/api/reports").json()["reports"]
    assert len(listing) == 1  # updated in place, not duplicated


def test_html_export(client):
    created = client.post("/api/reports", json=_report()).json()
    res = client.get("/api/html", params={"filename": created["jsonFilename"]})
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "<h1>Test</h1>" in res.text


def test_delete(client):
    created = client.post("/api/reports", json=_report()).json()
    assert client.delete(f"/api/delete/{created['jsonFilename']}").status_code == 200
    assert client.get("/api/reports").json()["reports"] == []


def test_path_traversal_blocked(client):
    # A filename containing traversal must never reach the filesystem: the guard
    # rejects it (400), the route doesn't match (404/405), or an encoded slash is
    # normalized away — in every case the request is refused, never served.
    for bad in ("..%2Fevil.json", "%2e%2e%2fevil.json"):
        assert client.delete(f"/api/delete/{bad}").status_code in (400, 404, 405)

    # And the guard itself, exercised directly, raises on a traversal filename.
    from app.reports.service import InvalidFilenameError, ReportService

    with pytest.raises(InvalidFilenameError):
        ReportService._guard_filename("../evil.json")


# ── report normalization (fixes "some sources open, others blank") ────────────


def test_wrapped_report_is_normalized(client):
    # A legacy report saved as {editingFilename, markdown, report:{...}} must be
    # unwrapped to {metadata, blocks} so the viewer renders it (not a blank page).
    import json
    from pathlib import Path

    reports_dir = Path(os.environ["REPORTS_DIR"])
    reports_dir.mkdir(parents=True, exist_ok=True)
    wrapped = {
        "editingFilename": None,
        "markdown": "# Wrapped",
        "report": {
            "metadata": {"incident_id": "INC9999", "title": "Wrapped One",
                         "caller": "x", "category": "c", "subcategory": "s", "date": "2026-07-03"},
            "blocks": [{"id": "h", "type": "heading", "level": 1, "content": "Wrapped"}],
        },
    }
    (reports_dir / "INC9999_wrapped.json").write_text(json.dumps(wrapped))

    got = client.get("/api/reports/content/INC9999_wrapped.json").json()
    assert got["metadata"]["incident_id"] == "INC9999"   # unwrapped, not blank
    assert got["blocks"][0]["content"] == "Wrapped"


def test_flat_report_passthrough(client):
    # An already-flat report is returned unchanged.
    created = client.post("/api/reports", json=_report(incident_id="INC5000")).json()
    got = client.get(f"/api/reports/content/{created['jsonFilename']}").json()
    assert got["metadata"]["incident_id"] == "INC5000"
    assert "report" not in got  # not double-wrapped
