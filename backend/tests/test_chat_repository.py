"""
Parity and isolation tests for the Postgres ChatRepository.

Two things are pinned here:

1. **Parity with the SQLite ChatStore.** The Postgres store was introduced as a
   drop-in replacement, so the same call sequence must produce the same results
   in both. The tests are parametrised over both implementations; a divergence
   fails on the Postgres side while the SQLite side stays green, which is what
   makes the failure readable.

2. **Ownership isolation.** Every read and write must refuse a conversation
   belonging to another identity. This is the property that becomes a security
   boundary once real users land, so it is asserted per-operation rather than
   once.

Skipped when no database is reachable, so the suite still runs on a machine
with nothing brought up. Set `TEST_DATABASE_URL` to point at another instance.
"""

from __future__ import annotations

import os
import uuid

import pytest

from app.chatbot.store import ChatStore
from app.db.chat_repository import ChatRepository
from app.db.models import Base
from app.db.session import Database

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://ntt:ntt@localhost:5433/ntt"
)

# This module drives the repository directly rather than through the app, so it
# opts out of the SQLite isolation default in conftest and uses real Postgres.
pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def pg_database():
    db = Database(TEST_DB_URL)
    if not db.ping():
        pytest.skip(f"no Postgres at {TEST_DB_URL}")
    db.create_all()
    yield db
    db.dispose()


@pytest.fixture
def pg_store(pg_database):
    return ChatRepository(pg_database)


@pytest.fixture
def sqlite_store(tmp_path):
    return ChatStore(tmp_path / "chat.db")


@pytest.fixture(params=["sqlite", "postgres"])
def store(request, sqlite_store, pg_store):
    """Both implementations, so parity failures name the divergent one."""
    return sqlite_store if request.param == "sqlite" else pg_store


@pytest.fixture
def alice():
    # Unique per test: the Postgres store is a shared, persistent database, so
    # fixed ids would let one test's rows satisfy another test's assertions.
    return f"alice-{uuid.uuid4().hex}"


@pytest.fixture
def bob():
    return f"bob-{uuid.uuid4().hex}"


# ── conversation lifecycle ────────────────────────────────────────────────────


def test_starts_empty(store, alice):
    assert store.list_conversations(alice) == []


def test_create_then_list(store, alice):
    conv = store.create_conversation(alice, "DNS outage")
    listed = store.list_conversations(alice)
    assert [c["id"] for c in listed] == [conv["id"]]
    assert listed[0]["title"] == "DNS outage"


def test_rename_and_delete(store, alice):
    conv = store.create_conversation(alice, "Old title")
    assert store.rename_conversation(alice, conv["id"], "New title") is True
    assert store.get_conversation(alice, conv["id"])["title"] == "New title"
    assert store.delete_conversation(alice, conv["id"]) is True
    assert store.get_conversation(alice, conv["id"]) is None


def test_delete_cascades_to_messages(store, alice):
    conv = store.create_conversation(alice)
    store.add_message(conv["id"], "user", "hello")
    store.delete_conversation(alice, conv["id"])
    assert store.list_messages(alice, conv["id"]) == []


# ── messages ──────────────────────────────────────────────────────────────────


def test_messages_round_trip_in_order(store, alice):
    conv = store.create_conversation(alice)
    store.add_message(conv["id"], "user", "How do I flush DNS?")
    store.add_message(
        conv["id"],
        "assistant",
        "Run resolvectl.",
        payload={"answer": "Run resolvectl.", "sources": ["inc_1.json"]},
    )
    msgs = store.list_messages(alice, conv["id"])
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["payload"]["sources"] == ["inc_1.json"]
    # has_image must survive as a bool, not the 0/1 the SQLite column stores.
    assert msgs[0]["has_image"] is False


def test_image_flag_persists(store, alice):
    conv = store.create_conversation(alice)
    store.add_message(conv["id"], "user", "", has_image=True)
    assert store.list_messages(alice, conv["id"])[0]["has_image"] is True


def test_get_message_payload(store, alice):
    conv = store.create_conversation(alice)
    msg = store.add_message(
        conv["id"], "assistant", "text", payload={"answer": "text"}
    )
    assert store.get_message_payload(alice, msg["id"]) == {"answer": "text"}


# ── feedback ──────────────────────────────────────────────────────────────────


def test_feedback_set_and_summarised(store, alice):
    conv = store.create_conversation(alice)
    msg = store.add_message(conv["id"], "assistant", "answer")
    before = store.feedback_summary()["up"]
    assert store.set_feedback(alice, msg["id"], 1) is True
    assert store.feedback_summary()["up"] == before + 1


def test_feedback_can_be_cleared(store, alice):
    conv = store.create_conversation(alice)
    msg = store.add_message(conv["id"], "assistant", "answer")
    store.set_feedback(alice, msg["id"], -1)
    assert store.set_feedback(alice, msg["id"], None) is True
    assert store.list_messages(alice, conv["id"])[0]["feedback"] is None


# ── corrections ───────────────────────────────────────────────────────────────


def test_correction_matches_on_partial_term_overlap(store, alice):
    """The query shares only some terms with the stored question.

    This is the case that a naive `websearch_to_tsquery` port fails: it ANDs
    every term, so the absent word "steps" would suppress an otherwise good
    match. Partial overlap must still retrieve.
    """
    store.add_correction(
        alice, "How do I clear the DNS cache?", "Use resolvectl flush-caches"
    )
    found = store.relevant_corrections("dns cache clearing steps")
    assert found, "partial term overlap should still match"
    assert found[0]["correction"] == "Use resolvectl flush-caches"


def test_correction_stemming_matches(store, alice):
    """"clearing" must match the indexed stem of "clear"."""
    store.add_correction(alice, "clear the router logs", "rotate them nightly")
    assert store.relevant_corrections("clearing router logs")


def test_correction_ignores_unrelated_query(store, alice):
    store.add_correction(alice, "restart the ingest worker", "systemctl restart")
    assert store.relevant_corrections("quantum banana zeppelin") == []


def test_correction_empty_query_returns_nothing(store, alice):
    store.add_correction(alice, "something", "anything")
    assert store.relevant_corrections("") == []
    assert store.relevant_corrections("   ") == []


# ── ownership isolation ───────────────────────────────────────────────────────


def test_other_user_cannot_see_conversation(store, alice, bob):
    store.create_conversation(alice, "private")
    assert store.list_conversations(bob) == []


@pytest.mark.parametrize(
    "operation",
    [
        lambda s, who, cid: s.get_conversation(who, cid),
        lambda s, who, cid: s.rename_conversation(who, cid, "hacked"),
        lambda s, who, cid: s.delete_conversation(who, cid),
        lambda s, who, cid: s.list_messages(who, cid),
    ],
    ids=["get", "rename", "delete", "list_messages"],
)
def test_other_user_is_refused_per_operation(store, alice, bob, operation):
    """Each operation independently refuses a conversation it does not own.

    Parametrised rather than combined: a single test would stop at the first
    failure and hide which operations leak.
    """
    conv = store.create_conversation(alice, "private")
    result = operation(store, bob, conv["id"])
    assert result in (None, False, []), f"leaked to another user: {result!r}"
    # The owner still has it — the refusal must not be a silent delete.
    assert store.get_conversation(alice, conv["id"]) is not None


def test_other_user_cannot_read_payload_or_rate(store, alice, bob):
    conv = store.create_conversation(alice)
    msg = store.add_message(conv["id"], "assistant", "secret", payload={"a": 1})
    assert store.get_message_payload(bob, msg["id"]) is None
    assert store.set_feedback(bob, msg["id"], 1) is False


# ── Postgres-only additions ───────────────────────────────────────────────────


def test_pinned_conversations_sort_first(pg_store, alice):
    pg_store.create_conversation(alice, "older")
    target = pg_store.create_conversation(alice, "pinned")
    pg_store.create_conversation(alice, "newest")
    assert pg_store.set_pinned(alice, target["id"], True) is True
    assert pg_store.list_conversations(alice)[0]["id"] == target["id"]


def test_unknown_user_reads_do_not_create_rows(pg_store):
    """Read paths must not mint a user for an id that has never written.

    Otherwise any unauthenticated probe would grow the users table.
    """
    ghost = f"ghost-{uuid.uuid4().hex}"
    assert pg_store.list_conversations(ghost) == []
    with pg_store.db.session() as s:
        from sqlalchemy import func, select

        from app.db.models import User

        count = s.execute(
            select(func.count()).select_from(User).where(User.subject == ghost)
        ).scalar_one()
    assert count == 0
