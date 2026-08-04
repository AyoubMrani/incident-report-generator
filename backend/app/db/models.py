"""
db/models.py — the platform schema.

Design notes that matter later:

* **Ids are TEXT, not serial.** The SQLite store minted `uuid4().hex` ids and
  they are already embedded in exported reports and client state. Keeping the
  same type makes the migration a copy rather than a re-keying exercise.

* **`users.subject` is the Keycloak `sub` claim**, not an email. Emails change;
  the OIDC subject does not. The pre-auth `X-Client-Id` UUIDs migrate in as
  users with `provider='legacy'`, so no history is orphaned when auth lands.

* **`messages.search_vector` is a generated column.** Postgres maintains it on
  write, so full-text search cannot drift out of sync with the message text —
  a trigger could be forgotten on a bulk insert, a generated column cannot.

* **`messages.embedding` is nullable** and backfilled asynchronously. Semantic
  search degrades to keyword-only for un-embedded rows rather than blocking the
  write path on an embedding model call.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Dimensionality of the sentence-transformers model already used for retrieval
# (all-MiniLM-L6-v2). Declared here because a pgvector column needs a fixed
# width; changing models means a migration, which is the honest cost.
EMBEDDING_DIM = 384


def _uid() -> str:
    return uuid.uuid4().hex


def _now() -> float:
    return time.time()


class Base(DeclarativeBase):
    pass


class User(Base):
    """A person. Created on first login from the OIDC token, or by migration."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    # OIDC `sub` for Keycloak users; the old X-Client-Id UUID for legacy rows.
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="keycloak")
    username: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # Roles are authoritative in the token; this mirror is for admin listing and
    # for offline queries ("who are the analysts?") when no token is present.
    roles: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=_now)
    last_seen_at: Mapped[float] = mapped_column(Float, nullable=False, default=_now)

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # One identity per (provider, subject): a Keycloak sub and a legacy
        # client id can coexist without colliding.
        UniqueConstraint("provider", "subject", name="uq_users_provider_subject"),
        Index("idx_users_subject", "subject"),
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, default="New conversation")
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=_now)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=_now)

    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Serves the sidebar query: this user's conversations, newest first,
        # pinned on top.
        Index("idx_conv_user_updated", "user_id", "pinned", "updated_at"),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    conversation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    has_image: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    feedback: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=_now)

    # Maintained by Postgres on every write — see module docstring.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(text, ''))", persisted=True),
        nullable=True,
    )
    # Backfilled out of band; NULL means "not embedded yet", not "no match".
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (
        CheckConstraint("role IN ('user','assistant','error')", name="ck_messages_role"),
        CheckConstraint(
            "feedback IS NULL OR feedback IN (-1, 1)", name="ck_messages_feedback"
        ),
        Index("idx_msg_conv", "conversation_id", "created_at"),
        # GIN over the generated tsvector: the keyword half of hybrid search.
        Index("idx_msg_search", "search_vector", postgresql_using="gin"),
        # Partial index — feedback is NULL for the overwhelming majority of rows,
        # and the metrics view only ever asks about the rated ones.
        Index(
            "idx_msg_feedback",
            "feedback",
            postgresql_where=(feedback.isnot(None)),
        ),
    )


class Correction(Base):
    """Human-supplied fix for a bad answer, fed back into future prompts."""

    __tablename__ = "corrections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    correction: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=_now)

    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(question, ''))", persisted=True),
        nullable=True,
    )

    __table_args__ = (
        Index("idx_corr_created", "created_at"),
        # Replaces the Python token-overlap scan in the SQLite store: matching
        # past corrections is now an indexed query, not a 200-row fetch.
        Index("idx_corr_search", "search_vector", postgresql_using="gin"),
    )


class Report(Base):
    """Catalog row for a report whose blobs live in MinIO.

    The blob is the source of truth for *content*; this row is the source of
    truth for *findability*. Listing reports is a SQL query over this table —
    not a directory scan plus a JSON parse per file, which is what the
    filesystem implementation had to do.
    """

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    incident_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # Sanitized [a-z0-9_] form used as the object key prefix and legacy filename.
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    author: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # Full metadata block, so the catalog can answer questions the typed columns
    # do not anticipate without fetching the blob.
    report_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    # MinIO coordinates. version_id is the bucket's object version, which is what
    # makes "show me this report as of last week" answerable.
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    version_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    created_by: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=_now)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=_now)
    deleted_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title,'') || ' ' || coalesce(incident_id,''))",
            persisted=True,
        ),
        nullable=True,
    )

    __table_args__ = (
        # **One row per stored object, not per incident.** The real corpus has
        # 8 incident ids that appear in two files each (an original and a
        # revision), so a unique constraint on incident_id would silently drop
        # one file from every such pair. Uniqueness belongs on object_key, which
        # is genuinely one-to-one with a blob.
        #
        # Partial on deleted_at IS NULL so re-saving a soft-deleted report
        # revives it rather than colliding with the tombstone.
        Index(
            "uq_reports_object_key_live",
            "object_key",
            unique=True,
            postgresql_where=(deleted_at.is_(None)),
        ),
        # Not unique: duplicate incident ids are expected, and this is the index
        # that answers "show me every version of INC0383926".
        Index("idx_reports_incident", "incident_id"),
        Index("idx_reports_updated", "updated_at"),
        Index("idx_reports_search", "search_vector", postgresql_using="gin"),
    )
