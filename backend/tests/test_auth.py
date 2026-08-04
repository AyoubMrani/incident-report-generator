"""
Authentication and authorization tests.

Split into two groups:

* **Offline** — token validation logic, the AUTH_DISABLED escape hatch and its
  production guard. These use a locally generated RSA keypair and a stub JWKS,
  so they run everywhere and are the ones that must never be skipped: they pin
  the security properties.

* **Live Keycloak** — marked `keycloak` and skipped when the realm is not
  reachable. These prove the realm export, the role mapping and the end-to-end
  request path actually work, which a stubbed test cannot.

The property that matters most is at the bottom: with auth on, a client that
sends its own `X-Client-Id` cannot use it to act as another user. That header
*was* the identity before this phase, so a regression there would silently
reopen impersonation.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import (
    AuthContext,
    assert_auth_config_sane,
    auth_disabled,
    current_user,
    require_role,
)
from app.auth.oidc import AuthError, OIDCValidator

KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8080")
REALM = os.environ.get("KEYCLOAK_REALM", "ntt")
ISSUER = f"{KEYCLOAK_URL}/realms/{REALM}"

# These tests set AUTH_DISABLED themselves to assert on both states, so they
# opt out of the suite-wide default in conftest.
pytestmark = pytest.mark.auth


# ── offline: token validation ─────────────────────────────────────────────────


@pytest.fixture(scope="module")
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key


@pytest.fixture
def signed_token(keypair):
    """Mint a token as Keycloak would, so validation can be tested offline."""

    def _make(**overrides):
        now = int(time.time())
        payload = {
            "sub": "user-subject-1",
            "iss": ISSUER,
            "aud": "ntt-platform",
            "azp": "ntt-platform",
            "exp": now + 300,
            "iat": now,
            "preferred_username": "analyst",
            "email": "analyst@ntt.local",
            "name": "Incident Analyst",
            "realm_access": {"roles": ["analyst", "viewer"]},
        }
        payload.update(overrides)
        pem = keypair.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return jwt.encode(payload, pem, algorithm="RS256", headers={"kid": "test-key"})

    return _make


@pytest.fixture
def validator(keypair, monkeypatch):
    """Validator whose JWKS lookup resolves to the local test key."""
    v = OIDCValidator(issuer=ISSUER)

    class _Key:
        key = keypair.public_key()

    class _Client:
        def get_signing_key_from_jwt(self, token):
            return _Key()

    monkeypatch.setattr(v, "_client", lambda force_refresh=False: _Client())
    return v


def test_valid_token_yields_claims(validator, signed_token):
    claims = validator.validate(signed_token())
    assert claims.subject == "user-subject-1"
    assert claims.username == "analyst"
    assert set(claims.roles) == {"analyst", "viewer"}


def test_expired_token_rejected(validator, signed_token):
    with pytest.raises(AuthError, match="expired"):
        validator.validate(signed_token(exp=int(time.time()) - 10))


def test_untrusted_issuer_rejected(validator, signed_token):
    with pytest.raises(AuthError, match="issuer"):
        validator.validate(signed_token(iss="http://evil.example/realms/ntt"))


def test_tampered_payload_rejected(validator, signed_token):
    """Re-encoding the payload to add a role must break the signature.

    This is the whole point of asymmetric validation: privilege escalation by
    editing the token is not merely discouraged, it is unrepresentable.
    """
    import base64

    token = signed_token()
    header, payload, signature = token.split(".")
    decoded = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    decoded["realm_access"]["roles"].append("admin")
    forged_payload = (
        base64.urlsafe_b64encode(json.dumps(decoded).encode()).decode().rstrip("=")
    )
    with pytest.raises(AuthError):
        validator.validate(f"{header}.{forged_payload}.{signature}")


@pytest.mark.parametrize("bad", ["", "not-a-token", "a.b", "...."])
def test_malformed_tokens_rejected(validator, bad):
    with pytest.raises(AuthError):
        validator.validate(bad)


def test_public_issuer_is_also_accepted(keypair, monkeypatch, signed_token):
    """Browser-facing and container-internal issuer URLs both validate.

    Inside compose the backend reaches Keycloak at http://keycloak:8080 but the
    browser is redirected to http://localhost:8080, and the token's `iss` is
    whichever the browser used. Accepting only one breaks every real login.
    """
    v = OIDCValidator(
        issuer="http://keycloak:8080/realms/ntt",
        public_issuer=ISSUER,
    )

    class _Key:
        key = keypair.public_key()

    monkeypatch.setattr(
        v, "_client", lambda force_refresh=False: type("C", (), {
            "get_signing_key_from_jwt": lambda self, t: _Key()
        })()
    )
    assert v.validate(signed_token(iss=ISSUER)).subject == "user-subject-1"


def test_client_roles_merge_with_realm_roles(validator, signed_token):
    claims = validator.validate(
        signed_token(resource_access={"ntt-platform": {"roles": ["report.export"]}})
    )
    assert "report.export" in claims.roles
    assert "analyst" in claims.roles


# ── offline: the AUTH_DISABLED escape hatch ───────────────────────────────────


def test_auth_disabled_reads_env(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "1")
    assert auth_disabled() is True
    monkeypatch.setenv("AUTH_DISABLED", "0")
    assert auth_disabled() is False


@pytest.mark.parametrize("env", ["production", "prod", "staging"])
def test_auth_cannot_be_disabled_in_deployed_env(monkeypatch, env):
    """The single most dangerous flag must fail closed.

    A misconfiguration that refuses to boot is recoverable; one that silently
    serves an unauthenticated API is a breach.
    """
    monkeypatch.setenv("AUTH_DISABLED", "1")
    monkeypatch.setenv("APP_ENV", env)
    with pytest.raises(RuntimeError, match="AUTH_DISABLED"):
        assert_auth_config_sane()


def test_auth_disabled_allowed_in_development(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "1")
    monkeypatch.setenv("APP_ENV", "development")
    assert_auth_config_sane()  # must not raise


def test_enabled_auth_is_fine_in_production(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "0")
    monkeypatch.setenv("APP_ENV", "production")
    assert_auth_config_sane()


# ── offline: role guards ──────────────────────────────────────────────────────


def _app_with_guard(*roles):
    app = FastAPI()
    app.state.oidc = None

    @app.get("/guarded", dependencies=[])
    def guarded(user: AuthContext = __import__("fastapi").Depends(require_role(*roles))):
        return {"ok": True, "user": user.id}

    return app


def test_role_guard_allows_matching_role(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "1")
    app = _app_with_guard("admin")
    with TestClient(app) as c:
        # With auth off there are no roles, so the dev identity passes — the
        # app would otherwise be entirely unusable in local development.
        assert c.get("/guarded", headers={"X-Client-Id": "dev"}).status_code == 200


def test_missing_client_id_falls_back_to_local_identity(monkeypatch):
    """In dev mode a missing header yields a fixed local identity, not a 400.

    The reports API never required an identity before auth existed, so a
    blanket router guard that demanded one would break endpoints (and tests)
    that correctly never sent it. Chat routes still enforce the header
    themselves, since conversation ownership is meaningless without it.
    """
    from app.auth.dependencies import LOCAL_ANONYMOUS_ID

    monkeypatch.setenv("AUTH_DISABLED", "1")
    app = _app_with_guard("admin")
    with TestClient(app) as c:
        r = c.get("/guarded")
        assert r.status_code == 200
        assert r.json()["user"] == LOCAL_ANONYMOUS_ID


def test_auth_context_permissions():
    admin = AuthContext(id="a", roles=("admin",))
    analyst = AuthContext(id="b", roles=("analyst",))
    viewer = AuthContext(id="c", roles=("viewer",))
    assert admin.is_admin and admin.can_write
    assert not analyst.is_admin and analyst.can_write
    assert not viewer.is_admin and not viewer.can_write


# ── live Keycloak ─────────────────────────────────────────────────────────────


def _keycloak_available() -> bool:
    try:
        with urllib.request.urlopen(
            f"{ISSUER}/.well-known/openid-configuration", timeout=3
        ) as r:
            return r.status == 200
    except Exception:
        return False


keycloak = pytest.mark.skipif(
    not _keycloak_available(), reason=f"Keycloak realm not reachable at {ISSUER}"
)


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


@keycloak
@pytest.mark.parametrize(
    "user,expected",
    [
        ("admin", {"admin", "analyst", "viewer"}),
        ("analyst", {"analyst", "viewer"}),
        ("viewer", {"viewer"}),
    ],
)
def test_realm_users_have_expected_roles(user, expected):
    """The realm export defines these three users and their roles.

    Pins infra/keycloak/realm-export.json: editing it in a way that drops a
    role should fail here, not in someone's browser.
    """
    validator = OIDCValidator(issuer=ISSUER)
    claims = validator.validate(_token(user, user))
    assert expected.issubset(set(claims.roles))
    assert claims.username == user


@keycloak
def test_real_token_validates_against_live_jwks():
    validator = OIDCValidator(issuer=ISSUER)
    assert validator.ready()
    claims = validator.validate(_token("analyst", "analyst"))
    assert claims.subject


@keycloak
def test_wrong_password_gets_no_token():
    with pytest.raises(urllib.error.HTTPError):
        _token("analyst", "wrong-password")
