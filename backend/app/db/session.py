"""
db/session.py — engine and session lifecycle.

One `Database` per process, built in the FastAPI lifespan. The engine owns a
connection pool, so constructing it per request would defeat pooling entirely.

Two deliberate choices:

* **`pool_pre_ping=True`.** Postgres in Docker restarts; a pooled connection
  that died with it would otherwise surface as a random `OperationalError` on
  whichever request happened to check it out. Pre-ping trades one cheap round
  trip for not serving that error to a user.

* **Connecting is not fatal at boot.** The app already degrades rather than
  crashes when Ollama is missing (`main.py`); the database follows the same
  rule, so the reports module and health endpoint stay reachable while
  Postgres is coming up.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# Host-side default. Port 5433 matches the compose mapping, which avoids the
# Postgres a developer machine usually already runs on 5432. Inside compose the
# backend gets an explicit DATABASE_URL pointing at postgres:5432.
DEFAULT_URL = "postgresql+psycopg://ntt:ntt@localhost:5433/ntt"


def get_database_url() -> str:
    """Resolve the connection URL.

    `DATABASE_URL` wins. The `postgres://` form that some tools emit is
    rewritten to SQLAlchemy's `postgresql+psycopg://` — a mismatch here fails
    with a driver error that reads like a missing dependency, which sends you
    looking in the wrong place.
    """
    url = os.environ.get("DATABASE_URL", DEFAULT_URL).strip()
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Database:
    """Engine + session factory, with the extension bootstrap the schema needs."""

    def __init__(self, url: str | None = None, *, echo: bool = False):
        self.url = url or get_database_url()
        self.engine: Engine = create_engine(
            self.url,
            echo=echo,
            pool_pre_ping=True,
            pool_size=int(os.environ.get("DB_POOL_SIZE", "5")),
            max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "10")),
            pool_recycle=1800,
            future=True,
        )
        self._session_factory = sessionmaker(
            bind=self.engine, expire_on_commit=False, future=True
        )

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def ping(self) -> bool:
        """True if the database answers. Used by /api/health and by startup."""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def ensure_extensions(self) -> None:
        """Install pgvector.

        Idempotent, and separate from Alembic on purpose: `CREATE EXTENSION`
        needs privileges a migration runner may not have in a managed
        environment, so it is one clearly-labelled step to grant rather than a
        surprise inside a migration.
        """
        with self.engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    def create_all(self) -> None:
        """Create tables directly from the models.

        For tests and first-run bootstrap. Alembic remains authoritative for
        deployed schema changes; this is the fast path that avoids running a
        migration chain to get an empty database.
        """
        from app.db.models import Base

        self.ensure_extensions()
        Base.metadata.create_all(self.engine)

    def dispose(self) -> None:
        self.engine.dispose()

    # ── sessions ──────────────────────────────────────────────────────────────

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Transactional scope: commit on success, roll back on any exception.

        Callers never manage the transaction themselves, so a handler that
        raises mid-write cannot leave a half-applied conversation behind.
        """
        s = self._session_factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()
