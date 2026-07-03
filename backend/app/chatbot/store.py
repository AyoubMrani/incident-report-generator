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
    created_at       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, created_at);
"""


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
                "SELECT id, role, text, has_image, payload, created_at "
                "FROM messages WHERE conversation_id=? ORDER BY created_at",
                (conversation_id,),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

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
            "created_at": r["created_at"],
        }
