"""
db/search.py — hybrid search over a user's chat history.

Two rankings, fused with the same RRF the knowledge-base retrieval uses:

* **Lexical** — Postgres full-text search over `messages.search_vector`, a
  generated column with a GIN index. Strong on the things a person actually
  remembers about a past conversation: an incident number, a table name, an
  error code.
* **Semantic** — cosine distance over `messages.embedding` (pgvector). Finds
  the conversation about "the login loop" when the query is "users can't sign
  in", which no keyword index can do.

Fusing them is the point. Pure vector search is famously weak on exact
identifiers — the embedding of `INC0383926` is near the embedding of every
other incident number — and pure keyword search misses paraphrase. RRF needs no
score calibration between cosine distance and `ts_rank`, whose scales are
unrelated.

Embeddings are optional. Where they are absent (not yet backfilled, or no model
loaded) the semantic ranking is empty and the fusion degrades to keyword-only
rather than returning nothing.

**Results are always scoped to one user.** Every query joins through
`conversations.user_id`; there is no "search everything" path to accidentally
call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Float, func, literal, select, text
from sqlalchemy.orm import Session

from app.db.models import Conversation, Message, User
from app.db.session import Database
from app.shared.fusion import rrf_rank

# How many candidates each arm contributes before fusion. Deeper than the page
# the user sees, so a result ranked modestly by both arms can still win — which
# is exactly the case RRF exists to handle.
CANDIDATE_LIMIT = 50

# Snippet rendering. Postgres does the highlighting so the matched terms are
# the *lexed* ones (stemming included), which a Python substring search would
# get wrong: searching "clearing" should highlight "clear".
_HEADLINE_OPTIONS = "StartSel=<mark>,StopSel=</mark>,MaxWords=28,MinWords=12,ShortWord=3,MaxFragments=2,FragmentDelimiter= … "


@dataclass
class SearchHit:
    message_id: str
    conversation_id: str
    conversation_title: str
    role: str
    text: str
    snippet: str
    created_at: float
    score: float
    matched_by: str  # "keyword", "semantic", or "both"

    def as_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "conversation_title": self.conversation_title,
            "role": self.role,
            "text": self.text,
            "snippet": self.snippet,
            "created_at": self.created_at,
            "score": round(self.score, 6),
            "matched_by": self.matched_by,
        }


class ChatSearch:
    """Hybrid search over the chat history of a single user."""

    def __init__(self, database: Database, embedder=None):
        self.db = database
        # Any object with .encode(text) -> vector. Injected rather than
        # constructed so search does not load a model of its own: the chatbot
        # already holds one, and a second copy would double resident memory.
        self.embedder = embedder

    # ── public API ────────────────────────────────────────────────────────────

    def search(
        self,
        client_id: str,
        query: str,
        *,
        limit: int = 20,
        conversation_id: str | None = None,
    ) -> list[SearchHit]:
        q = (query or "").strip()
        if not q:
            return []

        with self.db.session() as s:
            user_id = s.execute(
                select(User.id).where(User.subject == client_id)
            ).scalar_one_or_none()
            if user_id is None:
                return []

            keyword = self._keyword_candidates(s, user_id, q, conversation_id)
            semantic = self._semantic_candidates(s, user_id, q, conversation_id)

            if not keyword and not semantic:
                return []

            fused = rrf_rank(
                [mid for mid, _ in keyword],
                [mid for mid, _ in semantic],
            )
            top_ids = [mid for mid, _ in fused[:limit]]
            rows = self._hydrate(s, user_id, top_ids, q)

        kw_ids = {mid for mid, _ in keyword}
        sem_ids = {mid for mid, _ in semantic}
        scores = dict(fused)

        hits: list[SearchHit] = []
        for row in rows:
            mid = row.message_id
            matched = (
                "both"
                if mid in kw_ids and mid in sem_ids
                else ("keyword" if mid in kw_ids else "semantic")
            )
            hits.append(
                SearchHit(
                    message_id=mid,
                    conversation_id=row.conversation_id,
                    conversation_title=row.title,
                    role=row.role,
                    text=row.text,
                    snippet=row.snippet or _fallback_snippet(row.text),
                    created_at=row.created_at,
                    score=scores.get(mid, 0.0),
                    matched_by=matched,
                )
            )
        # `_hydrate` returns rows in an arbitrary order; restore fused ranking.
        order = {mid: i for i, mid in enumerate(top_ids)}
        hits.sort(key=lambda h: order.get(h.message_id, 1_000_000))
        return hits

    def search_conversations(
        self, client_id: str, query: str, *, limit: int = 20
    ) -> list[dict]:
        """Message hits collapsed to their conversations, best hit first.

        What the sidebar wants: "which of my chats is this in", not a flat list
        of messages where one conversation can occupy every slot.
        """
        hits = self.search(client_id, query, limit=CANDIDATE_LIMIT)
        seen: dict[str, dict] = {}
        for hit in hits:
            existing = seen.get(hit.conversation_id)
            if existing is None:
                seen[hit.conversation_id] = {
                    "conversation_id": hit.conversation_id,
                    "title": hit.conversation_title,
                    "snippet": hit.snippet,
                    "matched_by": hit.matched_by,
                    "score": hit.score,
                    "hit_count": 1,
                    "best_message_id": hit.message_id,
                    "created_at": hit.created_at,
                }
            else:
                existing["hit_count"] += 1
        return list(seen.values())[:limit]

    # ── ranking arms ──────────────────────────────────────────────────────────

    def _keyword_candidates(
        self,
        s: Session,
        user_id: str,
        query: str,
        conversation_id: str | None,
    ) -> list[tuple[str, float]]:
        """Full-text candidates, ranked by ts_rank.

        Terms are OR-ed, for the reason documented at length in
        `chat_repository.relevant_corrections`: AND-ing them (what
        websearch_to_tsquery does) makes a query fail as soon as it contains
        one word the target message happens not to use.
        """
        lexemes = _lexemes(s, query)
        if not lexemes:
            return []
        tsq = func.to_tsquery("english", " | ".join(lexemes))

        stmt = (
            select(
                Message.id,
                func.ts_rank(Message.search_vector, tsq).label("rank"),
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.user_id == user_id,
                Message.search_vector.op("@@")(tsq),
            )
            .order_by(text("rank DESC"))
            .limit(CANDIDATE_LIMIT)
        )
        if conversation_id:
            stmt = stmt.where(Message.conversation_id == conversation_id)
        return [(r.id, float(r.rank)) for r in s.execute(stmt).all()]

    def _semantic_candidates(
        self,
        s: Session,
        user_id: str,
        query: str,
        conversation_id: str | None,
    ) -> list[tuple[str, float]]:
        """Vector candidates by cosine distance, or [] when unavailable.

        Returning [] rather than raising is deliberate: with no embedder, or
        before the backfill has run, search must still work on keywords alone.
        """
        if self.embedder is None:
            return []
        try:
            vector = self.embedder.encode(query)
            vector = vector.tolist() if hasattr(vector, "tolist") else list(vector)
        except Exception:
            return []

        stmt = (
            select(
                Message.id,
                Message.embedding.cosine_distance(vector).label("distance"),
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.user_id == user_id,
                Message.embedding.isnot(None),
            )
            .order_by(text("distance ASC"))
            .limit(CANDIDATE_LIMIT)
        )
        if conversation_id:
            stmt = stmt.where(Message.conversation_id == conversation_id)
        try:
            rows = s.execute(stmt).all()
        except Exception:
            # pgvector missing or column unpopulated — degrade to keyword-only.
            return []
        return [(r.id, float(r.distance)) for r in rows]

    # ── hydration ─────────────────────────────────────────────────────────────

    def _hydrate(self, s: Session, user_id: str, ids: list[str], query: str):
        """Fetch display rows for the fused ids, with highlighted snippets."""
        if not ids:
            return []
        lexemes = _lexemes(s, query)
        if lexemes:
            tsq = func.to_tsquery("english", " | ".join(lexemes))
            snippet = func.ts_headline(
                "english", Message.text, tsq, _HEADLINE_OPTIONS
            )
        else:
            snippet = literal(None)

        stmt = (
            select(
                Message.id.label("message_id"),
                Message.conversation_id,
                Message.role,
                Message.text,
                Message.created_at,
                Conversation.title,
                snippet.label("snippet"),
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.user_id == user_id,
                Message.id.in_(ids),
            )
        )
        return s.execute(stmt).all()

    # ── embedding backfill ────────────────────────────────────────────────────

    def backfill_embeddings(self, batch_size: int = 200, max_batches: int = 100) -> int:
        """Embed messages that have no vector yet. Returns the count embedded.

        Run out of band (a startup task or a script), never on the write path:
        embedding is slow enough that doing it inline would make sending a chat
        message wait on the model.
        """
        if self.embedder is None:
            return 0

        total = 0
        for _ in range(max_batches):
            with self.db.session() as s:
                rows = s.execute(
                    select(Message.id, Message.text)
                    .where(Message.embedding.is_(None), Message.text != "")
                    .limit(batch_size)
                ).all()
                if not rows:
                    break
                for row in rows:
                    try:
                        vec = self.embedder.encode(row.text)
                        vec = vec.tolist() if hasattr(vec, "tolist") else list(vec)
                    except Exception:
                        continue
                    s.execute(
                        Message.__table__.update()
                        .where(Message.id == row.id)
                        .values(embedding=vec)
                    )
                    total += 1
        return total


# ── helpers ───────────────────────────────────────────────────────────────────


def _lexemes(s: Session, query: str) -> list[str]:
    """Lex a query through Postgres, so stemming matches the indexed vector.

    Splitting in Python would drift from the index: "clearing" must reduce to
    the same stem the stored tsvector holds for "clear".
    """
    rows = s.execute(
        select(
            func.unnest(func.tsvector_to_array(func.to_tsvector("english", query)))
        )
    ).scalars().all()
    # Bounded so a pasted stack trace cannot build a thousand-term tsquery.
    return [r for r in rows if r][:32]


def _fallback_snippet(text_value: str, width: int = 160) -> str:
    collapsed = re.sub(r"\s+", " ", text_value or "").strip()
    return collapsed[:width] + ("…" if len(collapsed) > width else "")
