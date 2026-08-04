"""
Suite-wide test configuration.

**Why this file exists.** Every API-level fixture in this suite points `CHAT_DB`
at a `tmp_path` and then asserts against an empty store — "no conversations
yet", "exactly one correction". That intent was satisfied for free when the
store was a per-test SQLite file. With Postgres as the default backend those
same tests would share one long-lived database, so rows from an earlier test
(or an earlier *run*) leak into the next one's assertions.

The fix is to honour the intent rather than weaken the assertions: any test that
builds the app gets the SQLite backend unless it explicitly asks for Postgres.
Isolation stays automatic and no existing test needed editing.

The Postgres path is still covered — `test_chat_repository.py` drives the real
repository directly, including the parity and ownership properties that matter.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _isolated_chat_backend(request, monkeypatch):
    """Default every test to the per-test SQLite store.

    Opt out with `@pytest.mark.postgres` when a test genuinely needs the real
    database. Applied before fixtures that construct the app, because
    `main.py` reads CHAT_BACKEND at lifespan time.
    """
    if request.node.get_closest_marker("postgres"):
        return
    monkeypatch.setenv("CHAT_BACKEND", "sqlite")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "postgres: test requires the real Postgres backend (not the SQLite "
        "isolation default applied by conftest)",
    )


@pytest.fixture(scope="session")
def postgres_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL", "postgresql+psycopg://ntt:ntt@localhost:5433/ntt"
    )
