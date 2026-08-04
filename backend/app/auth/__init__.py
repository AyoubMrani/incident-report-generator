"""
auth — OIDC authentication and role-based access control.

Identity comes from Keycloak as a signed JWT. The backend never sees a
password and never issues a token; it validates what the browser presents
against Keycloak's published signing keys.

    dependencies.py  FastAPI dependencies: current_user, require_role
    oidc.py          JWKS fetching, caching and token validation

The `AUTH_DISABLED=1` escape hatch keeps the pre-auth `X-Client-Id` behaviour,
so the test suite and a bare `uvicorn` run work without Keycloak running. It is
refused when the app is not obviously local — see `dependencies.py`.
"""

from app.auth.dependencies import (
    AuthContext,
    current_user,
    optional_user,
    require_admin,
    require_analyst,
    require_role,
)
from app.auth.oidc import AuthError, OIDCValidator

__all__ = [
    "AuthContext",
    "AuthError",
    "OIDCValidator",
    "current_user",
    "optional_user",
    "require_admin",
    "require_analyst",
    "require_role",
]
