"""
chatbot/store.py — server-side persistence for chat conversations (SQLite).

Zero-infra durability: a single SQLite file (path from CHAT_DB env, default
data/chat.db). Conversations and messages are keyed by a client id the browser
generates and stores, so history survives server restarts and syncs across tabs
on the same client. This is deliberately auth-free for now; when real user
accounts land, `client_id` becomes `user_id` and nothing else changes.

Concurrency: SQLite with WAL + a short busy timeout handles the low write volume
of a chat app fine. Each call opens a short-lived connection (thread-safe under
FastAPI's threadpool); the schema is created once at construction.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    client_id   TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT 'New conversation',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_client ON conversations(client_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             TEXT NOT NULL,          -- 'user' | 'assistant' | 'error'
    text             TEXT NOT NULL DEFAULT '',
    has_image        INTEGER NOT NULL DEFAULT 0,
    payload          TEXT,                   -- JSON: assistant answer / attachments / links
    feedback         INTEGER,                -- thumbs: 1 (up), -1 (down), NULL (none)
    created_at       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS corrections (
    id          TEXT PRIMARY KEY,
    client_id   TEXT NOT NULL,
    question    TEXT NOT NULL,          -- the incident question that got a bad answer
    correction  TEXT NOT NULL,          -- the human-provided correct guidance
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_corr_created ON corrections(created_at DESC);
"""


_STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "is",
         "are", "how", "do", "i", "my", "it", "with", "why", "what", "this"}


def _tokens(text: str) -> set[str]:
    import re
    return {t for t in re.findall(r"[a-z0-9_]+", (text or "").lower())
            if t not in _STOP and len(t) > 2}


def _now() -> float:
    return time.time()


def _uid() -> str:
    return uuid.uuid4().hex


class ChatStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)
            self._migrate(c)

    @staticmethod
    def _migrate(c: sqlite3.Connection) -> None:
        """Additive migrations for DBs created before a column existed."""
        cols = {r["name"] for r in c.execute("PRAGMA table_info(messages)")}
        if "feedback" not in cols:
            c.execute("ALTER TABLE messages ADD COLUMN feedback INTEGER")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ── conversations ─────────────────────────────────────────────────────────

    def list_conversations(self, client_id: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, title, created_at, updated_at "
                "FROM conversations WHERE client_id=? ORDER BY updated_at DESC",
                (client_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def create_conversation(self, client_id: str, title: str = "New conversation") -> dict:
        cid = _uid()
        now = _now()
        with self._conn() as c:
            c.execute(
                "INSERT INTO conversations(id, client_id, title, created_at, updated_at) "
                "VALUES(?,?,?,?,?)",
                (cid, client_id, title, now, now),
            )
        return {"id": cid, "title": title, "created_at": now, "updated_at": now}

    def get_conversation(self, client_id: str, conversation_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT id, title, created_at, updated_at FROM conversations "
                "WHERE id=? AND client_id=?",
                (conversation_id, client_id),
            ).fetchone()
        return dict(row) if row else None

    def rename_conversation(self, client_id: str, conversation_id: str, title: str) -> bool:
        with self._conn() as c:
            cur = c.execute(
                "UPDATE conversations SET title=?, updated_at=? WHERE id=? AND client_id=?",
                (title, _now(), conversation_id, client_id),
            )
            return cur.rowcount > 0

    def delete_conversation(self, client_id: str, conversation_id: str) -> bool:
        with self._conn() as c:
            cur = c.execute(
                "DELETE FROM conversations WHERE id=? AND client_id=?",
                (conversation_id, client_id),
            )
            return cur.rowcount > 0

    def _touch(self, conn: sqlite3.Connection, conversation_id: str) -> None:
        conn.execute(
            "UPDATE conversations SET updated_at=? WHERE id=?",
            (_now(), conversation_id),
        )

    # ── messages ──────────────────────────────────────────────────────────────

    def list_messages(self, client_id: str, conversation_id: str) -> list[dict]:
        with self._conn() as c:
            # Ownership check folded into the join on client_id.
            owns = c.execute(
                "SELECT 1 FROM conversations WHERE id=? AND client_id=?",
                (conversation_id, client_id),
            ).fetchone()
            if not owns:
                return []
            rows = c.execute(
                "SELECT id, role, text, has_image, payload, feedback, created_at "
                "FROM messages WHERE conversation_id=? ORDER BY created_at",
                (conversation_id,),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def get_message_payload(self, client_id: str, message_id: str) -> dict | None:
        """The stored answer object for a message the client owns."""
        with self._conn() as c:
            row = c.execute(
                "SELECT m.payload FROM messages m "
                "JOIN conversations c ON c.id = m.conversation_id "
                "WHERE m.id=? AND c.client_id=?",
                (message_id, client_id),
            ).fetchone()
        if not row or not row["payload"]:
            return None
        return json.loads(row["payload"])

    def set_feedback(self, client_id: str, message_id: str, value: int | None) -> bool:
        """Set a thumbs rating (1 / -1 / None) on an assistant message the client
        owns. Ownership is enforced by joining back to the conversation."""
        with self._conn() as c:
            row = c.execute(
                "SELECT m.id FROM messages m "
                "JOIN conversations c ON c.id = m.conversation_id "
                "WHERE m.id=? AND c.client_id=?",
                (message_id, client_id),
            ).fetchone()
            if not row:
                return False
            c.execute(
                "UPDATE messages SET feedback=? WHERE id=?", (value, message_id)
            )
            return True

    def feedback_summary(self) -> dict:
        """Aggregate thumbs across all assistant messages (for a metrics view)."""
        with self._conn() as c:
            up = c.execute("SELECT COUNT(*) FROM messages WHERE feedback=1").fetchone()[0]
            down = c.execute("SELECT COUNT(*) FROM messages WHERE feedback=-1").fetchone()[0]
            corr = c.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]
        return {"up": up, "down": down, "total_rated": up + down, "corrections": corr}

    def report_feedback_scores(self) -> dict[str, int]:
        """Net thumbs per cited incident id — see the Postgres repository for
        the rationale. Parsed in Python because payload is a JSON text column
        here; the row count is bounded by rated messages, which is small."""
        scores: dict[str, int] = {}
        with self._conn() as c:
            rows = c.execute(
                "SELECT payload, feedback FROM messages "
                "WHERE feedback IS NOT NULL AND payload IS NOT NULL"
            ).fetchall()
        for row in rows:
            try:
                payload = json.loads(row["payload"]) or {}
            except (ValueError, TypeError):
                continue
            for source in payload.get("retrieval") or []:
                if not isinstance(source, dict):
                    continue
                inc = str(source.get("incident_id") or "").strip().lower()
                if inc:
                    scores[inc] = scores.get(inc, 0) + int(row["feedback"])
        return scores

    # ── learned corrections (feedback that improves future answers) ────────────

    def add_correction(self, client_id: str, question: str, correction: str) -> dict:
        cid = _uid()
        now = _now()
        with self._conn() as c:
            c.execute(
                "INSERT INTO corrections(id, client_id, question, correction, created_at) "
                "VALUES(?,?,?,?,?)",
                (cid, client_id, question.strip(), correction.strip(), now),
            )
        return {"id": cid, "question": question, "correction": correction, "created_at": now}

    def list_corrections(self, limit: int = 200) -> list[dict]:
        """All stored corrections, newest first — see the Postgres repository."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, question, correction, created_at FROM corrections "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_correction(self, correction_id: str) -> bool:
        """Remove a correction. Returns False when it does not exist."""
        with self._conn() as c:
            cur = c.execute("DELETE FROM corrections WHERE id=?", (correction_id,))
            return cur.rowcount > 0

    def relevant_corrections(self, query: str, limit: int = 3) -> list[dict]:
        """Return past corrections whose question overlaps this query's terms.

        A lightweight token-overlap match (no embedding needed): a correction is
        relevant if its stored question shares meaningful words with the current
        query. Cheap, local, and good enough to surface the right past fix.
        """
        q_tokens = _tokens(query)
        if not q_tokens:
            return []
        with self._conn() as c:
            rows = c.execute(
                "SELECT question, correction FROM corrections ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
        scored = []
        for r in rows:
            overlap = len(q_tokens & _tokens(r["question"]))
            if overlap:
                scored.append((overlap, {"question": r["question"], "correction": r["correction"]}))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:limit]]

    def add_message(
        self,
        conversation_id: str,
        role: str,
        text: str = "",
        has_image: bool = False,
        payload: dict[str, Any] | None = None,
    ) -> dict:
        mid = _uid()
        now = _now()
        with self._conn() as c:
            c.execute(
                "INSERT INTO messages(id, conversation_id, role, text, has_image, payload, created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    mid,
                    conversation_id,
                    role,
                    text,
                    1 if has_image else 0,
                    json.dumps(payload) if payload is not None else None,
                    now,
                ),
            )
            self._touch(c, conversation_id)
        return {
            "id": mid,
            "role": role,
            "text": text,
            "has_image": has_image,
            "payload": payload,
            "created_at": now,
        }

    @staticmethod
    def _row_to_message(r: sqlite3.Row) -> dict:
        return {
            "id": r["id"],
            "role": r["role"],
            "text": r["text"],
            "has_image": bool(r["has_image"]),
            "payload": json.loads(r["payload"]) if r["payload"] else None,
            "feedback": r["feedback"],
            "created_at": r["created_at"],
        }
