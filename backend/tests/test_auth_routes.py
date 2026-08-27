"""
Route-level authentication tests against a live Keycloak.

These run the real request path — token in, verified subject out, store keyed
on it — which the offline tests in test_auth.py deliberately do not cover.

The headline property is `test_client_id_header_cannot_impersonate`: before this
phase `X-Client-Id` *was* the identity, so a regression that let it override the
token would silently reopen impersonation of any user whose id was guessed.

Skipped as a module when Keycloak is not up, so the suite still runs offline.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

import jwt
import pytest
from fastapi.testclient import TestClient

KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8080")
REALM = os.environ.get("KEYCLOAK_REALM", "ntt")
ISSUER = f"{KEYCLOAK_URL}/realms/{REALM}"


def _keycloak_available() -> bool:
    try:
        with urllib.request.urlopen(
            f"{ISSUER}/.well-known/openid-configuration", timeout=3
        ) as r:
            return r.status == 200
    except Exception:
        return False


pytestmark = [
    pytest.mark.postgres,
    pytest.mark.auth,
    pytest.mark.skipif(
        not _keycloak_available(), reason=f"Keycloak not reachable at {ISSUER}"
    ),
]


def _token(username: str, password: str) -> str:
    data = urllib.parse.urlencode(
        {
            "client_id": "ntt-platform",
            "username": username,
            "password": password,
            "grant_type": "password",
        }
    ).encode()
    with urllib.request.urlopen(
        f"{ISSUER}/protocol/openid-connect/token", data, timeout=10
    ) as r:
        return json.load(r)["access_token"]


def _subject(token: str) -> str:
    return jwt.decode(token, options={"verify_signature": False})["sub"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    """App with auth ON, Postgres chat store, chatbot and MinIO out of the way."""
    monkeypatch.setenv("AUTH_DISABLED", "0")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("CHAT_BACKEND", "postgres")
    monkeypatch.setenv("STORAGE_BACKEND", "filesystem")
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("DISABLE_CHATBOT", "1")
    monkeypatch.setenv(
        "DATABASE_URL",
        os.environ.get(
            "TEST_DATABASE_URL", "postgresql+psycopg://ntt:ntt@localhost:5433/ntt"
        ),
    )
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def analyst_headers():
    return {"Authorization": f"Bearer {_token('analyst', 'analyst')}"}


@pytest.fixture
def viewer_headers():
    return {"Authorization": f"Bearer {_token('viewer', 'viewer')}"}


# ── unauthenticated access ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path", ["/api/me", "/api/conversations", "/api/feedback/summary"]
)
def test_protected_routes_require_a_token(client, path):
    r = client.get(path)
    assert r.status_code in (401, 403), f"{path} returned {r.status_code}"


# Endpoints the browser must reach before it has a token.
PUBLIC_PATHS = {"/api/health", "/api/auth/config"}


def test_every_endpoint_is_protected_or_deliberately_public(client):
    """Enumerate the real route table and probe each one without a token.

    Written after an audit found ten unauthenticated endpoints, including
    `DELETE /api/delete/{filename}` answering 200 — anyone who could reach the
    port could destroy incident records. Source inspection missed it because
    the handlers *looked* fine; only probing behaviour showed the gap.

    This asserts over whatever routes exist, so a new endpoint added without
    auth fails here instead of shipping.
    """
    app = client.app
    unprotected: list[str] = []

    for path, operations in app.openapi()["paths"].items():
        if not path.startswith("/api"):
            continue
        for method in operations:
            verb = method.upper()
            if verb not in ("GET", "POST", "PATCH", "PUT", "DELETE"):
                continue
            url = (
                path.replace("{conversation_id}", "probe")
                .replace("{message_id}", "probe")
                .replace("{filename}", "probe.json")
            )
            response = client.request(
                verb, url, json={} if verb in ("POST", "PATCH", "PUT") else None
            )
            if path in PUBLIC_PATHS:
                assert response.status_code == 200, (
                    f"{verb} {path} should be publicly reachable, "
                    f"got {response.status_code}"
                )
            elif response.status_code not in (401, 403):
                unprotected.append(f"{verb} {path} -> {response.status_code}")

    assert not unprotected, "endpoints reachable without a token: " + ", ".join(
        unprotected
    )


def test_viewer_cannot_delete_a_report(client, viewer_headers):
    """Role separation on the destructive path, not just authentication."""
    r = client.request(
        "DELETE", "/api/delete/anything.json", headers=viewer_headers
    )
    assert r.status_code == 403


def test_viewer_cannot_save_a_report(client, viewer_headers):
    r = client.post("/api/reports", headers=viewer_headers, json={})
    assert r.status_code == 403


def test_viewer_can_still_read_reports(client, viewer_headers):
    """Read-only must mean read-*able*, or the role is useless."""
    assert client.get("/api/reports", headers=viewer_headers).status_code == 200


def test_feedback_summary_is_admin_only(client, analyst_headers):
    """It aggregates across all users, so an analyst must not see it."""
    assert client.get("/api/feedback/summary", headers=analyst_headers).status_code == 403
    admin = {"Authorization": f"Bearer {_token('admin', 'admin')}"}
    assert client.get("/api/feedback/summary", headers=admin).status_code == 200


def test_listing_corrections_is_admin_only(client, analyst_headers):
    """Corrections are global — any user's correction steers everyone's
    answers — so reading them exposes other people's activity."""
    assert client.get("/api/corrections", headers=analyst_headers).status_code == 403
    admin = {"Authorization": f"Bearer {_token('admin', 'admin')}"}
    assert client.get("/api/corrections", headers=admin).status_code == 200


def test_deleting_a_correction_is_admin_only(client, analyst_headers):
    r = client.delete("/api/corrections/does-not-exist", headers=analyst_headers)
    assert r.status_code == 403
    admin = {"Authorization": f"Bearer {_token('admin', 'admin')}"}
    # Authorised, but the id is not real: 404 rather than 403.
    r = client.delete("/api/corrections/does-not-exist", headers=admin)
    assert r.status_code == 404


def test_an_analyst_can_still_submit_a_correction(client, analyst_headers):
    """Review is admin-only; *contributing* must stay open or the loop dies."""
    r = client.post(
        "/api/corrections",
        headers=analyst_headers,
        json={"question": "dns cache", "correction": "flush the resolver cache"},
    )
    assert r.status_code == 200


def test_garbage_token_rejected(client):
    r = client.get("/api/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_non_bearer_scheme_rejected(client):
    r = client.get("/api/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert r.status_code == 401


def test_health_and_auth_config_stay_public(client):
    """The browser needs these before it has a token."""
    assert client.get("/api/health").status_code == 200
    cfg = client.get("/api/auth/config")
    assert cfg.status_code == 200
    assert cfg.json()["enabled"] is True


# ── identity ──────────────────────────────────────────────────────────────────


def test_me_returns_token_identity(client, analyst_headers):
    me = client.get("/api/me", headers=analyst_headers).json()
    assert me["username"] == "analyst"
    assert me["authenticated"] is True
    assert set(me["roles"]) >= {"analyst", "viewer"}
    assert me["can_write"] is True
    assert me["is_admin"] is False


def test_viewer_cannot_write(client, viewer_headers):
    me = client.get("/api/me", headers=viewer_headers).json()
    assert me["can_write"] is False
    assert me["is_admin"] is False


def test_admin_has_admin_flag(client):
    headers = {"Authorization": f"Bearer {_token('admin', 'admin')}"}
    me = client.get("/api/me", headers=headers).json()
    assert me["is_admin"] is True


# ── the property that matters ─────────────────────────────────────────────────


def test_client_id_header_cannot_impersonate(client, analyst_headers):
    """A supplied X-Client-Id must be ignored in favour of the token subject.

    Before auth, this header *was* the identity. If it still won, anyone could
    read anyone else's conversations by guessing an id.
    """
    token = analyst_headers["Authorization"].split()[1]
    real_subject = _subject(token)

    store = client.app.state.chat_store
    conv = store.create_conversation(real_subject, "Analyst private")
    store.add_message(conv["id"], "user", "sensitive incident detail")

    try:
        # Same token, but claiming to be someone else via the legacy header.
        forged = {**analyst_headers, "X-Client-Id": "somebody-else"}
        listed = client.get("/api/conversations", headers=forged).json()
        # The header was ignored: we still see the analyst's own conversations.
        assert any(c["id"] == conv["id"] for c in listed)

        # And a bare forged header with no token is refused outright.
        assert client.get(
            "/api/conversations", headers={"X-Client-Id": real_subject}
        ).status_code == 401
    finally:
        store.delete_conversation(real_subject, conv["id"])


def test_conversations_are_isolated_between_users(client, analyst_headers, viewer_headers):
    analyst_sub = _subject(analyst_headers["Authorization"].split()[1])
    store = client.app.state.chat_store
    conv = store.create_conversation(analyst_sub, "Private to analyst")
    store.add_message(conv["id"], "user", "secret")

    try:
        assert client.get(
            f"/api/conversations/{conv['id']}/messages", headers=viewer_headers
        ).status_code == 404
        r = client.get(
            f"/api/conversations/{conv['id']}/messages", headers=analyst_headers
        )
        assert r.status_code == 200
        assert len(r.json()) == 1
    finally:
        store.delete_conversation(analyst_sub, conv["id"])
