"""
auth/oidc.py — JWT validation against Keycloak.

Validation is asymmetric: Keycloak signs with its private key, the backend
verifies with the public key it publishes at the JWKS endpoint. No shared
secret is configured anywhere, so a leaked backend config cannot mint tokens.

Details that are easy to get wrong and matter:

* **JWKS is cached, but refetched on an unknown `kid`.** Keycloak rotates
  signing keys; a purely time-based cache would reject every token for up to
  the TTL after a rotation. Keying the refresh on "I have never seen this key
  id" makes rotation invisible to users while still bounding fetches.

* **Two issuers are accepted.** Inside compose the backend reaches Keycloak at
  `http://keycloak:8080`, while the browser is redirected to
  `http://localhost:8080`. The `iss` claim carries whichever the *browser*
  used, so validating against only the internal URL rejects every real login.

* **Signature verification is never optional.** There is no "skip verification"
  flag anywhere in this module. Auth can be disabled wholesale for local dev
  (see dependencies.py), but a token that is checked is checked properly.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.request import urlopen

import jwt
from jwt import PyJWKClient

DEFAULT_ISSUER = "http://localhost:8080/realms/ntt"
JWKS_CACHE_SECONDS = 600


class AuthError(Exception):
    """Token missing, malformed, expired, or not trusted."""


@dataclass
class Claims:
    """The subset of the token this application acts on."""

    subject: str
    username: str = ""
    email: str = ""
    display_name: str = ""
    roles: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class OIDCValidator:
    """Validates access tokens issued by a Keycloak realm."""

    def __init__(
        self,
        issuer: str | None = None,
        *,
        public_issuer: str | None = None,
        audience: str | None = None,
        verify_audience: bool = False,
    ):
        self.issuer = (issuer or os.environ.get("OIDC_ISSUER", DEFAULT_ISSUER)).rstrip("/")
        public = public_issuer or os.environ.get("OIDC_PUBLIC_ISSUER", "")
        self.public_issuer = public.rstrip("/") if public else ""
        self.audience = audience or os.environ.get("OIDC_CLIENT_ID", "ntt-platform")

        # Keycloak puts the client id in `azp` and only sets `aud` when an
        # audience mapper is configured. Verifying `aud` by default would
        # reject valid tokens from a realm whose mapper was not imported, so
        # it is opt-in via OIDC_VERIFY_AUDIENCE=1.
        self.verify_audience = verify_audience or (
            os.environ.get("OIDC_VERIFY_AUDIENCE", "0") == "1"
        )

        self._jwks_client: PyJWKClient | None = None
        self._jwks_fetched_at = 0.0
        self._seen_kids: set[str] = set()
        self._lock = threading.Lock()

    # ── issuer / discovery ────────────────────────────────────────────────────

    @property
    def jwks_uri(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/certs"

    def accepted_issuers(self) -> list[str]:
        out = [self.issuer]
        if self.public_issuer and self.public_issuer != self.issuer:
            out.append(self.public_issuer)
        return out

    def _client(self, force_refresh: bool = False) -> PyJWKClient:
        with self._lock:
            stale = time.time() - self._jwks_fetched_at > JWKS_CACHE_SECONDS
            if self._jwks_client is None or stale or force_refresh:
                self._jwks_client = PyJWKClient(self.jwks_uri, cache_keys=False)
                self._jwks_fetched_at = time.time()
            return self._jwks_client

    def ready(self) -> bool:
        """True if the issuer's discovery document is reachable."""
        try:
            with urlopen(
                f"{self.issuer}/.well-known/openid-configuration", timeout=5
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    # ── validation ────────────────────────────────────────────────────────────

    def validate(self, token: str) -> Claims:
        """Verify signature, expiry and issuer; return the claims.

        Raises AuthError on anything that makes the token untrustworthy. The
        message is deliberately generic to the caller — a 401 body should not
        explain *why* a token failed, since that helps an attacker tune it.
        """
        if not token:
            raise AuthError("missing token")

        try:
            kid = jwt.get_unverified_header(token).get("kid", "")
        except jwt.PyJWTError as exc:
            raise AuthError("malformed token") from exc

        # A kid we have never seen means Keycloak probably rotated its keys;
        # refetch once before deciding the token is bad.
        force = bool(kid) and kid not in self._seen_kids
        try:
            signing_key = self._client(force_refresh=force).get_signing_key_from_jwt(
                token
            )
        except Exception as exc:
            try:
                signing_key = self._client(force_refresh=True).get_signing_key_from_jwt(
                    token
                )
            except Exception:
                raise AuthError("token signing key not found") from exc

        self._seen_kids.add(kid)

        options = {"verify_aud": self.verify_audience}
        last_error: Exception | None = None
        for issuer in self.accepted_issuers():
            try:
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256", "RS384", "RS512", "ES256"],
                    issuer=issuer,
                    audience=self.audience if self.verify_audience else None,
                    options=options,
                )
                return self._to_claims(payload)
            except jwt.ExpiredSignatureError as exc:
                # Expiry does not depend on which issuer string matched, so
                # there is nothing to gain from trying the other one.
                raise AuthError("token expired") from exc
            except jwt.InvalidIssuerError as exc:
                last_error = exc
                continue
            except jwt.PyJWTError as exc:
                raise AuthError("invalid token") from exc

        raise AuthError("untrusted issuer") from last_error

    @staticmethod
    def _to_claims(payload: dict[str, Any]) -> Claims:
        realm_roles = (payload.get("realm_access") or {}).get("roles") or []
        # Roles from the realm plus this client's own roles, deduplicated with
        # order preserved so the list reads predictably in logs and the UI.
        resource = payload.get("resource_access") or {}
        client_roles: list[str] = []
        for entry in resource.values():
            client_roles.extend((entry or {}).get("roles") or [])

        seen: set[str] = set()
        roles = [
            r for r in [*realm_roles, *client_roles] if not (r in seen or seen.add(r))
        ]

        return Claims(
            subject=payload.get("sub", ""),
            username=payload.get("preferred_username", ""),
            email=payload.get("email", ""),
            display_name=payload.get("name", "") or payload.get("preferred_username", ""),
            roles=roles,
            raw=payload,
        )
