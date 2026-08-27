"""
db/chat_repository.py — the Postgres implementation of the chat store.

Deliberately exposes the **same method signatures as the SQLite `ChatStore`**,
including the `client_id` first argument. That keeps the swap to a one-line
change in `main.py`: routers, tests and the frontend contract are untouched,
so a storage migration cannot smuggle in a behaviour change.

The `client_id` argument is now resolved to a `users.id` rather than compared
as an opaque string. `_resolve_user` maps either form — an authenticated
Keycloak subject or a legacy browser UUID — onto a row, creating one on first
sight. That is what makes the pre-auth history keep working after auth lands.

Ownership is enforced the same way it was in SQLite: every read and write joins
back to `conversations.user_id`, so a guessed conversation id belonging to
another user returns nothing rather than leaking a row.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import Conversation, Correction, Message, User
from app.db.session import Database


def _now() -> float:
    return time.time()


def _uid() -> str:
    return uuid.uuid4().hex


class ChatRepository:
    """Postgres-backed conversation store."""

    def __init__(self, database: Database):
        self.db = database

    # ── identity ──────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_user(
        s: Session,
        client_id: str,
        *,
        provider: str = "legacy",
        create: bool = True,
    ) -> str | None:
        """Map an incoming identity onto `users.id`.

        `client_id` is either a Keycloak subject (when auth is on) or the old
        browser UUID (when it is off, and for every row written before auth).
        Both are looked up by `subject`, so the same person keeps their history
        across the switch as long as the identifier is stable.

        The insert is ON CONFLICT DO NOTHING on (provider, subject): two
        concurrent first requests from the same new user would otherwise race
        and one would fail the unique constraint.
        """
        row = s.execute(
            select(User.id).where(User.subject == client_id)
        ).scalar_one_or_none()
        if row is not None:
            return row
        if not create:
            return None

        new_id = _uid()
        s.execute(
            pg_insert(User)
            .values(
                id=new_id,
                subject=client_id,
                provider=provider,
                username=client_id[:255],
                roles=[],
                created_at=_now(),
                last_seen_at=_now(),
            )
            .on_conflict_do_nothing(index_elements=["provider", "subject"])
        )
        # Re-select rather than trusting new_id: on conflict the winning row is
        # the other request's, and returning our discarded id would orphan the
        # conversation about to be written against it.
        return s.execute(
            select(User.id).where(User.subject == client_id)
        ).scalar_one()

    # ── conversations ─────────────────────────────────────────────────────────

    def list_conversations(self, client_id: str) -> list[dict]:
        with self.db.session() as s:
            uid = self._resolve_user(s, client_id, create=False)
            if uid is None:
                return []
            rows = s.execute(
                select(
                    Conversation.id,
                    Conversation.title,
                    Conversation.pinned,
                    Conversation.created_at,
                    Conversation.updated_at,
                )
                .where(Conversation.user_id == uid)
                .order_by(Conversation.pinned.desc(), Conversation.updated_at.desc())
            ).all()
        return [
            {
                "id": r.id,
                "title": r.title,
                "pinned": r.pinned,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in rows
        ]

    def create_conversation(
        self, client_id: str, title: str = "New conversation"
    ) -> dict:
        with self.db.session() as s:
            uid = self._resolve_user(s, client_id)
            cid, now = _uid(), _now()
            s.add(
                Conversation(
                    id=cid,
                    user_id=uid,
                    title=title,
                    pinned=False,
                    created_at=now,
                    updated_at=now,
                )
            )
        return {
            "id": cid,
            "title": title,
            "pinned": False,
            "created_at": now,
            "updated_at": now,
        }

    def get_conversation(self, client_id: str, conversation_id: str) -> dict | None:
        with self.db.session() as s:
            uid = self._resolve_user(s, client_id, create=False)
            if uid is None:
                return None
            r = s.execute(
                select(
                    Conversation.id,
                    Conversation.title,
                    Conversation.pinned,
                    Conversation.created_at,
                    Conversation.updated_at,
                ).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == uid,
                )
            ).one_or_none()
        if r is None:
            return None
        return {
            "id": r.id,
            "title": r.title,
            "pinned": r.pinned,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }

    def rename_conversation(
        self, client_id: str, conversation_id: str, title: str
    ) -> bool:
        with self.db.session() as s:
            uid = self._resolve_user(s, client_id, create=False)
            if uid is None:
                return False
            res = s.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id, Conversation.user_id == uid)
                .values(title=title, updated_at=_now())
            )
            return res.rowcount > 0

    def set_pinned(self, client_id: str, conversation_id: str, pinned: bool) -> bool:
        """Pin a conversation to the top of the sidebar. New in the Postgres
        store; the SQLite one had no such column."""
        with self.db.session() as s:
            uid = self._resolve_user(s, client_id, create=False)
            if uid is None:
                return False
            res = s.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id, Conversation.user_id == uid)
                .values(pinned=pinned)
            )
            return res.rowcount > 0

    def delete_conversation(self, client_id: str, conversation_id: str) -> bool:
        with self.db.session() as s:
            uid = self._resolve_user(s, client_id, create=False)
            if uid is None:
                return False
            res = s.execute(
                delete(Conversation).where(
                    Conversation.id == conversation_id, Conversation.user_id == uid
                )
            )
            # Messages go with it via ON DELETE CASCADE — enforced by Postgres,
            # not by a second statement that could be skipped on an error path.
            return res.rowcount > 0

    # ── messages ──────────────────────────────────────────────────────────────

    def list_messages(self, client_id: str, conversation_id: str) -> list[dict]:
        with self.db.session() as s:
            uid = self._resolve_user(s, client_id, create=False)
            if uid is None:
                return []
            owns = s.execute(
                select(Conversation.id).where(
                    Conversation.id == conversation_id, Conversation.user_id == uid
                )
            ).scalar_one_or_none()
            if owns is None:
                return []
            rows = s.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
            ).scalars().all()
            return [self._to_dict(m) for m in rows]

    def add_message(
        self,
        conversation_id: str,
        role: str,
        text: str = "",
        has_image: bool = False,
        payload: dict[str, Any] | None = None,
    ) -> dict:
        """Append a message and bump the conversation's updated_at.

        Note the signature takes no client_id: it mirrors the SQLite store,
        where the caller has already established ownership by opening the turn.
        """
        mid, now = _uid(), _now()
        with self.db.session() as s:
            s.add(
                Message(
                    id=mid,
                    conversation_id=conversation_id,
                    role=role,
                    text=text,
                    has_image=bool(has_image),
                    payload=payload,
                    created_at=now,
                )
            )
            s.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(updated_at=now)
            )
        return {
            "id": mid,
            "role": role,
            "text": text,
            "has_image": has_image,
            "payload": payload,
            "created_at": now,
        }

    def get_message_payload(self, client_id: str, message_id: str) -> dict | None:
        with self.db.session() as s:
            uid = self._resolve_user(s, client_id, create=False)
            if uid is None:
                return None
            payload = s.execute(
                select(Message.payload)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(Message.id == message_id, Conversation.user_id == uid)
            ).scalar_one_or_none()
        return payload or None

    def set_feedback(self, client_id: str, message_id: str, value: int | None) -> bool:
        with self.db.session() as s:
            uid = self._resolve_user(s, client_id, create=False)
            if uid is None:
                return False
            owned = s.execute(
                select(Message.id)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(Message.id == message_id, Conversation.user_id == uid)
            ).scalar_one_or_none()
            if owned is None:
                return False
            s.execute(
                update(Message).where(Message.id == message_id).values(feedback=value)
            )
            return True

    def feedback_summary(self) -> dict:
        with self.db.session() as s:
            up = s.execute(
                select(func.count()).select_from(Message).where(Message.feedback == 1)
            ).scalar_one()
            down = s.execute(
                select(func.count()).select_from(Message).where(Message.feedback == -1)
            ).scalar_one()
            corr = s.execute(
                select(func.count()).select_from(Correction)
            ).scalar_one()
        return {
            "up": up,
            "down": down,
            "total_rated": up + down,
            "corrections": corr,
        }

    def report_feedback_scores(self) -> dict[str, int]:
        """Net thumbs per cited incident id, e.g. {"inc0012001": 2}.

        Read off the stored answer payload rather than a join table: the answer
        already records which reports it cited (`retrieval[].incident_id`), so
        the signal is derivable from data we keep anyway — no schema change and
        no risk of the two drifting apart.

        A rated answer with an empty `retrieval` (an ungrounded AI suggestion)
        contributes nothing, which is correct: there is no report to reward.
        """
        sql = text(
            """
            SELECT lower(trim(src.incident_id)) AS incident_id,
                   SUM(m.feedback)              AS net
              FROM messages AS m
              CROSS JOIN LATERAL jsonb_to_recordset(
                       COALESCE(m.payload -> 'retrieval', '[]'::jsonb)
                   ) AS src(incident_id text)
             WHERE m.feedback IS NOT NULL
               AND src.incident_id IS NOT NULL
               AND trim(src.incident_id) <> ''
             GROUP BY 1
            """
        )
        with self.db.session() as s:
            rows = s.execute(sql).all()
        return {r.incident_id: int(r.net) for r in rows}

    # ── learned corrections ───────────────────────────────────────────────────

    def add_correction(self, client_id: str, question: str, correction: str) -> dict:
        with self.db.session() as s:
            uid = self._resolve_user(s, client_id)
            cid, now = _uid(), _now()
            s.add(
                Correction(
                    id=cid,
                    user_id=uid,
                    question=question.strip(),
                    correction=correction.strip(),
                    created_at=now,
                )
            )
        return {
            "id": cid,
            "question": question,
            "correction": correction,
            "created_at": now,
        }

    def list_corrections(self, limit: int = 200) -> list[dict]:
        """All stored corrections, newest first — for admin review.

        Corrections are injected into every future matching prompt and are not
        scoped to their author, so they need to be inspectable and removable by
        someone: an unreviewed, permanent write path into the prompt is the
        part of this loop most worth being able to undo.
        """
        with self.db.session() as s:
            rows = s.execute(
                select(
                    Correction.id,
                    Correction.question,
                    Correction.correction,
                    Correction.created_at,
                )
                .order_by(Correction.created_at.desc())
                .limit(limit)
            ).all()
        return [
            {
                "id": r.id,
                "question": r.question,
                "correction": r.correction,
                "created_at": r.created_at,
            }
            for r in rows
        ]

    def delete_correction(self, correction_id: str) -> bool:
        """Remove a correction. Returns False when it does not exist."""
        with self.db.session() as s:
            result = s.execute(
                delete(Correction).where(Correction.id == correction_id)
            )
            return bool(result.rowcount)

    def relevant_corrections(self, query: str, limit: int = 3) -> list[dict]:
        """Past corrections whose question overlaps this query.

        The SQLite store fetched 200 rows and scored token overlap in Python;
        this is the same semantics as an indexed query.

        **The terms are OR-ed, not AND-ed.** `websearch_to_tsquery` and
        `plainto_tsquery` both AND, which is wrong here: asking "dns cache
        clearing steps" would then fail to match a stored correction for "how
        do I clear the DNS cache?" because `steps` is absent. A correction
        sharing two of four terms is still the one worth showing. `ts_rank`
        then does the job the Python overlap count did — more shared terms
        sorts higher — so recall comes from OR and precision from the ranking.
        """
        q = (query or "").strip()
        if not q:
            return []

        with self.db.session() as s:
            # Lex the query through Postgres itself rather than splitting in
            # Python: this applies the same stemming and stop-word list used to
            # build the indexed vector, so "clearing" matches the stored
            # "clear". A hand-rolled tokenizer would drift from the index.
            lexemes = s.execute(
                select(func.unnest(func.tsvector_to_array(
                    func.to_tsvector("english", q)
                )))
            ).scalars().all()
            if not lexemes:
                return []

            # Lexemes come from to_tsvector, so they are already normalised and
            # contain no tsquery operators — safe to join. Bound the count so a
            # pathological question cannot build a huge query.
            tsq = func.to_tsquery("english", " | ".join(lexemes[:32]))
            rows = s.execute(
                select(Correction.question, Correction.correction)
                .where(Correction.search_vector.op("@@")(tsq))
                .order_by(
                    func.ts_rank(Correction.search_vector, tsq).desc(),
                    Correction.created_at.desc(),
                )
                .limit(limit)
            ).all()
        return [{"question": r.question, "correction": r.correction} for r in rows]

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _to_dict(m: Message) -> dict:
        return {
            "id": m.id,
            "role": m.role,
            "text": m.text,
            "has_image": bool(m.has_image),
            "payload": m.payload,
            "feedback": m.feedback,
            "created_at": m.created_at,
        }
