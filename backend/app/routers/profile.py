"""
routers/profile.py — the signed-in user's own profile.

Display name and avatar only. Everything that governs *access* — username,
email, password, roles — stays in Keycloak, which is the identity provider;
letting the app edit those would put two sources of truth on the same fields
and let a user rewrite the identity their token asserts.

The avatar is a data URI stored on the user row. Avatars are a few KB, are
always needed alongside the user record, and putting them in MinIO would mean a
second round trip on every page load for no benefit at this scale.
"""

from __future__ import annotations

import base64
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.dependencies import AuthContext, current_user
from app.db.models import User

router = APIRouter(tags=["profile"], dependencies=[Depends(current_user)])

# 256 KB of base64 ≈ 190 KB of image — ample for an avatar, and small enough
# that a row stays cheap to read. Rejecting oversized uploads here keeps a
# 5 MB photo from being embedded in every /api/me response.
MAX_AVATAR_CHARS = 256 * 1024

_DATA_URI = re.compile(r"^data:image/(png|jpe?g|webp|gif);base64,([A-Za-z0-9+/=]+)$")


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    # Empty string clears the avatar; None leaves it untouched. The two are
    # deliberately distinct so "remove my picture" is expressible.
    avatar_url: str | None = None


def _database(request: Request):
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(
            status_code=501,
            detail="Profiles require the Postgres backend",
        )
    return db


def _validate_avatar(value: str) -> str:
    """Accept a small, well-formed image data URI, or reject it.

    Validated rather than trusted: this string is rendered back into an <img>
    for every viewer of the app, so a `data:text/html` or `javascript:` value
    would be stored XSS. Only image MIME types with decodable base64 pass.
    """
    if value == "":
        return ""
    if len(value) > MAX_AVATAR_CHARS:
        raise HTTPException(
            status_code=413,
            detail="Image is too large. Please use one under ~190 KB.",
        )
    match = _DATA_URI.match(value.strip())
    if not match:
        raise HTTPException(
            status_code=400,
            detail="Avatar must be a PNG, JPEG, WebP or GIF data URI.",
        )
    try:
        base64.b64decode(match.group(2), validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Malformed image data.") from exc
    return value.strip()


@router.get("/api/profile")
def get_profile(
    request: Request, user: AuthContext = Depends(current_user)
) -> dict:
    """Stored profile for the caller, falling back to their token claims."""
    db = _database(request)
    with db.session() as s:
        row = s.execute(
            select(User.display_name, User.avatar_url).where(User.subject == user.id)
        ).one_or_none()

    return {
        "display_name": (row.display_name if row else "") or user.display_name,
        "avatar_url": (row.avatar_url if row else "") or "",
    }


@router.patch("/api/profile")
def update_profile(
    body: ProfileUpdate,
    request: Request,
    user: AuthContext = Depends(current_user),
) -> dict:
    """Update the caller's own display name and/or avatar.

    Scoped to the caller by construction: the row is selected by the token's
    subject, so there is no id parameter that could address someone else.
    """
    db = _database(request)
    values: dict = {}

    if body.display_name is not None:
        values["display_name"] = body.display_name.strip()[:120]
    if body.avatar_url is not None:
        values["avatar_url"] = _validate_avatar(body.avatar_url)

    if not values:
        raise HTTPException(status_code=400, detail="Nothing to update")

    with db.session() as s:
        target = s.execute(
            select(User).where(User.subject == user.id)
        ).scalar_one_or_none()
        if target is None:
            # First write from a user who has only ever read: create the row so
            # the profile has somewhere to live.
            target = User(
                subject=user.id,
                provider="keycloak" if user.authenticated else "legacy",
                username=user.username or user.id[:255],
                email=user.email,
                roles=list(user.roles),
                created_at=time.time(),
                last_seen_at=time.time(),
            )
            s.add(target)
            s.flush()
        for key, value in values.items():
            setattr(target, key, value)
        result = {
            "display_name": target.display_name,
            "avatar_url": target.avatar_url,
        }

    return {"success": True, **result}
