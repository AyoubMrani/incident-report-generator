"""
auth/dependencies.py — FastAPI dependencies for identity and roles.

Every protected route depends on `current_user`, which returns an
`AuthContext`. The context's `.id` is the value that used to be the
`X-Client-Id` header, so handlers and the chat store did not change shape when
auth landed: what changed is that the value is now *proven* rather than
asserted by the caller.

## The AUTH_DISABLED escape hatch

`AUTH_DISABLED=1` restores the old behaviour: identity is whatever
`X-Client-Id` says. The test suite and a bare `uvicorn` run need this, since
neither has a Keycloak.

It is also the single most dangerous flag in the codebase — it turns off
authentication for the whole application. So it is refused when the process
looks like a real deployment: if `AUTH_DISABLED=1` is set while `APP_ENV` is
production, the app fails to start rather than silently serving an open API.
A misconfiguration that fails loudly at boot is recoverable; one that quietly
disables auth is a breach.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException, Request, status

from app.auth.oidc import AuthError, Claims, OIDCValidator

# Role names, mirroring infra/keycloak/realm-export.json.
ROLE_ADMIN = "admin"
ROLE_ANALYST = "analyst"
ROLE_VIEWER = "viewer"

# Writers are analysts and admins; viewers are read-only.
WRITE_ROLES = (ROLE_ADMIN, ROLE_ANALYST)


def auth_disabled() -> bool:
    return os.environ.get("AUTH_DISABLED", "0").strip() in ("1", "true", "yes")


def assert_auth_config_sane() -> None:
    """Refuse to run with auth off in a deployed environment.

    Called from the app lifespan so the failure happens at boot, not on the
    first unauthenticated request.
    """
    env = os.environ.get("APP_ENV", "development").strip().lower()
    if auth_disabled() and env in ("production", "prod", "staging"):
        raise RuntimeError(
            f"AUTH_DISABLED=1 is not allowed when APP_ENV={env!r}. "
            "Unset AUTH_DISABLED or set APP_ENV=development."
        )


@dataclass(frozen=True)
class AuthContext:
    """The authenticated caller.

    `id` is the stable identifier the data layer keys on: the OIDC subject when
    authenticated, or the X-Client-Id value when auth is disabled. Both are
    resolved to a `users` row by the chat repository, which is why the same
    handler code works either way.
    """

    id: str
    username: str = ""
    email: str = ""
    display_name: str = ""
    roles: tuple[str, ...] = field(default_factory=tuple)
    authenticated: bool = True

    def has_role(self, *roles: str) -> bool:
        return any(r in self.roles for r in roles)

    @property
    def is_admin(self) -> bool:
        return ROLE_ADMIN in self.roles

    @property
    def can_write(self) -> bool:
        # With auth off there is no role information, so the dev identity is
        # allowed to write — otherwise the whole app would be read-only in dev.
        return not self.authenticated or self.has_role(*WRITE_ROLES)

    @classmethod
    def from_claims(cls, claims: Claims) -> "AuthContext":
        return cls(
            id=claims.subject,
            username=claims.username,
            email=claims.email,
            display_name=claims.display_name,
            roles=tuple(claims.roles),
            authenticated=True,
        )


def get_validator(request: Request) -> OIDCValidator:
    """The validator built once in the app lifespan."""
    validator = getattr(request.app.state, "oidc", None)
    if validator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )
    return validator


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


# Identity used in dev mode when no X-Client-Id is supplied. The reports API
# never took an identity before auth existed, so requiring one here would break
# clients (and tests) that correctly never sent it. Chat routes still demand the
# header explicitly — see `routers/chat.py::_client_id` — because conversation
# ownership is meaningless without one.
LOCAL_ANONYMOUS_ID = "local-anonymous"


def current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_client_id: str | None = Header(default=None),
) -> AuthContext:
    """Resolve the caller, or raise 401.

    With auth disabled this reproduces the old header-based identity: the
    header when present, and a fixed local identity when not. Routes that
    genuinely need a per-client id enforce it themselves, which keeps this
    dependency usable as a blanket router guard without changing the contract
    of endpoints that never had one.
    """
    if auth_disabled():
        client = (x_client_id or "").strip() or LOCAL_ANONYMOUS_ID
        return AuthContext(
            id=client,
            username=client[:32],
            display_name="Local user",
            roles=(),
            authenticated=False,
        )

    token = _bearer_token(authorization)
    try:
        claims = get_validator(request).validate(token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not claims.subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has no subject",
        )
    return AuthContext.from_claims(claims)


def optional_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_client_id: str | None = Header(default=None),
) -> AuthContext | None:
    """Like `current_user`, but returns None instead of raising.

    For endpoints that are richer when signed in but still work anonymously.
    """
    try:
        return current_user(request, authorization, x_client_id)
    except HTTPException:
        return None


def require_role(*roles: str):
    """Dependency factory guarding a route behind one or more roles.

        @router.post(..., dependencies=[Depends(require_role(ROLE_ADMIN))])

    Returns 403, not 401: the caller proved who they are, they just are not
    allowed. Conflating the two makes a permissions bug look like a login bug.
    """

    def _guard(user: AuthContext = Depends(current_user)) -> AuthContext:
        # With auth off there are no roles to check; the dev identity passes.
        if not user.authenticated:
            return user
        if not user.has_role(*roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(roles)}",
            )
        return user

    return _guard


require_admin = require_role(ROLE_ADMIN)
require_analyst = require_role(ROLE_ADMIN, ROLE_ANALYST)
