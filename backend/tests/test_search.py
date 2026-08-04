"""
Hybrid chat-search tests.

Structured around what each arm is *for*:

* keyword search must nail exact identifiers (INC numbers, command names,
  table names) — the things people actually remember about an old chat;
* semantic search must find a conversation described in different words;
* fusion must not let either arm suppress the other;
* and every result must be scoped to the asking user.

The semantic tests need the sentence-transformers model. They are marked
`slow` and skipped when it is not already cached, so the default suite stays
fast and offline; the keyword and isolation tests always run.
"""

from __future__ import annotations

import os
import uuid

import pytest

from app.db.chat_repository import ChatRepository
from app.db.search import ChatSearch
from app.db.session import Database
from app.shared.fusion import RRF_K, rrf_fuse, rrf_rank

pytestmark = pytest.mark.postgres

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://ntt:ntt@localhost:5433/ntt"
)

# Four conversations whose vocabularies barely overlap, so a query matching the
# right one cannot be luck.
SEED = [
    (
        "VPN tunnel down",
        [
            ("user", "VPN clients cannot establish tunnel after the maintenance window"),
            ("assistant", "Check the IKE phase 1 proposal and restart the ipsec service"),
        ],
    ),
    (
        "DNS flapping",
        [
            ("user", "Intermittent DNS resolution failures for internal services"),
            ("assistant", "Flush the resolver cache with resolvectl flush-caches"),
        ],
    ),
    (
        "Login problems",
        [
            ("user", "users are stuck in a redirect loop and cannot sign in"),
            ("assistant", "The IdP metadata rotated; re-import the SAML descriptor"),
        ],
    ),
    (
        "Deadlocks",
        [
            ("user", "Recurring deadlocks on the orders table during the flash sale"),
            ("assistant", "Add an index on orders(customer_id, created_at)"),
        ],
    ),
]


@pytest.fixture(scope="module")
def database():
    db = Database(TEST_DB_URL)
    if not db.ping():
        pytest.skip(f"no Postgres at {TEST_DB_URL}")
    db.create_all()
    yield db
    db.dispose()


@pytest.fixture
def user(database):
    """A fresh identity per test, with the seed conversations loaded."""
    uid = f"search-user-{uuid.uuid4().hex}"
    repo = ChatRepository(database)
    for title, messages in SEED:
        conv = repo.create_conversation(uid, title)
        for role, text in messages:
            repo.add_message(conv["id"], role, text)
    return uid


@pytest.fixture
def keyword_search(database):
    """Search with no embedder — the keyword-only degradation path."""
    return ChatSearch(database)


@pytest.fixture(scope="module")
def embedder():
    """The real embedding model, if it is already cached locally."""
    try:
        from sentence_transformers import SentenceTransformer

        from app.chatbot.config import EMBED_MODEL_NAME

        return SentenceTransformer(EMBED_MODEL_NAME)
    except Exception as exc:  # noqa: BLE001 — availability probe
        pytest.skip(f"embedding model unavailable: {exc}")


@pytest.fixture
def hybrid_search(database, embedder, user):
    search = ChatSearch(database, embedder=embedder)
    search.backfill_embeddings()
    return search


# ── fusion arithmetic ─────────────────────────────────────────────────────────


def test_rrf_rewards_agreement_between_rankings():
    """An item ranked well by both arms must beat one ranked first by only one.

    This is the property that makes fusion worth doing; without it the two
    arms are just concatenated.
    """
    fused = rrf_fuse(["a", "b", "c"], ["b", "a", "d"])
    assert fused["b"] > fused["c"]
    assert fused["a"] > fused["c"]


def test_rrf_handles_rankings_of_different_lengths():
    """The lexical arm returns only what it matched; the dense arm ranks all."""
    fused = rrf_fuse(["a", "b", "c", "d"], ["c"])
    assert fused["c"] > fused["a"]


def test_rrf_k_matches_the_paper_constant():
    assert RRF_K == 60
    assert rrf_fuse(["x"])["x"] == pytest.approx(1.0 / 60)


def test_rrf_rank_is_ordered_best_first():
    ranked = rrf_rank(["a", "b"], ["b", "a"])
    assert [item for item, _ in ranked] == ["b", "a"] or [
        item for item, _ in ranked
    ] == ["a", "b"]
    assert ranked[0][1] >= ranked[1][1]


# ── keyword arm ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "query,expected",
    [
        ("resolvectl flush-caches", "DNS flapping"),
        ("IKE phase 1", "VPN tunnel down"),
        ("orders table", "Deadlocks"),
        ("SAML descriptor", "Login problems"),
    ],
)
def test_keyword_search_finds_exact_identifiers(
    keyword_search, user, query, expected
):
    """Exact identifiers are where pure vector search is weakest and this
    arm is strongest — the reason the search is hybrid at all."""
    hits = keyword_search.search(user, query, limit=5)
    assert hits, f"no hits for {query!r}"
    assert expected in {h.conversation_title for h in hits}


def test_keyword_search_stems(keyword_search, user):
    """"deadlock" must match the indexed "deadlocks"."""
    assert keyword_search.search(user, "deadlock", limit=5)


def test_snippet_highlights_matched_terms(keyword_search, user):
    hits = keyword_search.search(user, "resolvectl", limit=1)
    assert hits
    assert "<mark>" in hits[0].snippet


def test_empty_query_returns_nothing(keyword_search, user):
    assert keyword_search.search(user, "") == []
    assert keyword_search.search(user, "   ") == []


def test_unrelated_query_returns_nothing(keyword_search, user):
    assert keyword_search.search(user, "zeppelin quantum banana") == []


def test_search_without_embedder_still_works(keyword_search, user):
    """No model loaded must degrade to keyword-only, not fail."""
    assert keyword_search.embedder is None
    hits = keyword_search.search(user, "resolvectl", limit=5)
    assert hits and all(h.matched_by == "keyword" for h in hits)


# ── semantic arm ──────────────────────────────────────────────────────────────


@pytest.mark.slow
@pytest.mark.parametrize(
    "query,expected",
    [
        ("cannot authenticate to the portal", "Login problems"),
        ("name resolution is broken", "DNS flapping"),
        ("database lock contention at peak traffic", "Deadlocks"),
        ("remote workers cannot connect securely", "VPN tunnel down"),
    ],
)
def test_semantic_search_finds_paraphrases(hybrid_search, user, query, expected):
    """Queries that share almost no vocabulary with the stored conversation.

    "database lock contention at peak traffic" has no word in common with
    "Recurring deadlocks on the orders table during the flash sale"; only the
    vector arm can bridge that, which is what earns pgvector its place.
    """
    hits = hybrid_search.search(user, query, limit=3)
    assert hits, f"no hits for {query!r}"
    assert expected in {h.conversation_title for h in hits}


@pytest.mark.slow
def test_hybrid_marks_how_a_result_matched(hybrid_search, user):
    hits = hybrid_search.search(user, "resolvectl flush-caches", limit=5)
    assert hits
    assert {h.matched_by for h in hits} <= {"keyword", "semantic", "both"}


@pytest.mark.slow
def test_backfill_is_idempotent(hybrid_search, user):
    """A second pass must find nothing left to embed."""
    assert hybrid_search.backfill_embeddings() == 0


# ── grouping ──────────────────────────────────────────────────────────────────


def test_grouped_results_collapse_to_conversations(keyword_search, user):
    """The sidebar wants conversations, not a list where one chat fills every
    slot with its individual messages."""
    grouped = keyword_search.search_conversations(user, "DNS resolution failures")
    ids = [g["conversation_id"] for g in grouped]
    assert len(ids) == len(set(ids)), "a conversation appeared twice"
    assert all("title" in g and "snippet" in g for g in grouped)


# ── isolation ─────────────────────────────────────────────────────────────────


def test_search_never_crosses_users(keyword_search, user, database):
    """The property that makes search safe to expose at all."""
    stranger = f"stranger-{uuid.uuid4().hex}"
    repo = ChatRepository(database)
    conv = repo.create_conversation(stranger, "Someone else's incident")
    repo.add_message(conv["id"], "user", "resolvectl flush-caches on their host")

    mine = keyword_search.search(user, "resolvectl", limit=50)
    assert conv["id"] not in {h.conversation_id for h in mine}

    theirs = keyword_search.search(stranger, "resolvectl", limit=50)
    assert {h.conversation_id for h in theirs} == {conv["id"]}


def test_unknown_user_gets_no_results(keyword_search):
    assert keyword_search.search(f"ghost-{uuid.uuid4().hex}", "anything") == []


def test_scoping_to_one_conversation(keyword_search, user, database):
    repo = ChatRepository(database)
    convs = repo.list_conversations(user)
    target = next(c for c in convs if c["title"] == "DNS flapping")
    hits = keyword_search.search(
        user, "cannot", limit=20, conversation_id=target["id"]
    )
    assert all(h.conversation_id == target["id"] for h in hits)
