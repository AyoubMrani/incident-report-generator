#!/usr/bin/env python3
"""
Migrate chat history from the SQLite store into Postgres.

    python scripts/migrate_to_postgres.py --dry-run     # report, change nothing
    python scripts/migrate_to_postgres.py               # migrate
    python scripts/migrate_to_postgres.py --verify      # compare counts only

Properties this script is built to have, because a data migration you cannot
re-run is a data migration you run at 2am and cannot fix:

* **Idempotent.** Rows are upserted on their primary key, which is preserved
  from SQLite. Running it twice migrates nothing the second time; running it
  after new chats have arrived migrates only those.
* **Non-destructive.** The SQLite file is opened read-only (`mode=ro`) and is
  never modified or deleted. Rollback is "point CHAT_BACKEND back at sqlite".
* **Order-safe.** Users, then conversations, then messages: every foreign key
  has its target already committed. Orphaned messages (a conversation deleted
  without its messages, which the old schema allowed if foreign_keys was off)
  are reported and skipped rather than aborting the run.
* **Verified.** Finishes by comparing row counts on both sides and exits
  non-zero on a mismatch, so a partial migration fails loudly in CI or a shell
  chain instead of looking successful.

Every pre-auth `client_id` becomes a user with `provider='legacy'`. When
Keycloak lands, a returning person gets a *new* row keyed on their OIDC subject
— their old history stays under the legacy id. Linking the two is a deliberate
follow-up (`--link-legacy` below) rather than a guess, because matching a
browser UUID to a human is exactly the kind of automatic inference that
silently hands one person another person's conversations.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.db.models import Conversation, Correction, Message, User  # noqa: E402
from app.db.session import Database  # noqa: E402

DEFAULT_SQLITE = REPO_ROOT / "data" / "chat.db"


def _open_sqlite(path: Path) -> sqlite3.Connection:
    """Read-only handle. A typo in this script must not be able to damage the
    source of truth we are migrating away from."""
    if not path.exists():
        raise SystemExit(f"no SQLite database at {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def _rows(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    if not _table_exists(conn, table):
        return []
    return conn.execute(f"SELECT * FROM {table}").fetchall()


def _col(row: sqlite3.Row, name: str, default=None):
    """Tolerate schema drift between older and newer SQLite files."""
    return row[name] if name in row.keys() else default


def migrate(sqlite_path: Path, db: Database, *, dry_run: bool) -> dict:
    src = _open_sqlite(sqlite_path)
    stats = {
        "users": 0,
        "conversations": 0,
        "messages": 0,
        "corrections": 0,
        "skipped_orphan_messages": 0,
        "skipped_bad_role": 0,
    }

    conversations = _rows(src, "conversations")
    messages = _rows(src, "messages")
    corrections = _rows(src, "corrections")

    # Every identity that appears anywhere becomes a legacy user.
    client_ids = {r["client_id"] for r in conversations if r["client_id"]}
    client_ids |= {
        _col(r, "client_id") for r in corrections if _col(r, "client_id")
    }

    now = time.time()
    valid_conv_ids = {r["id"] for r in conversations}

    if dry_run:
        for m in messages:
            if m["conversation_id"] not in valid_conv_ids:
                stats["skipped_orphan_messages"] += 1
            elif m["role"] not in ("user", "assistant", "error"):
                stats["skipped_bad_role"] += 1
        stats["users"] = len(client_ids)
        stats["conversations"] = len(conversations)
        stats["messages"] = (
            len(messages)
            - stats["skipped_orphan_messages"]
            - stats["skipped_bad_role"]
        )
        stats["corrections"] = len(corrections)
        return stats

    with db.session() as s:
        # ── users ─────────────────────────────────────────────────────────────
        # Deterministic id from the client UUID, so re-running maps the same
        # client onto the same user row instead of creating a duplicate.
        user_by_client: dict[str, str] = {}
        for client_id in sorted(client_ids):
            existing = s.execute(
                select(User.id).where(
                    User.provider == "legacy", User.subject == client_id
                )
            ).scalar_one_or_none()
            if existing:
                user_by_client[client_id] = existing
                continue
            uid = uuid.uuid5(uuid.NAMESPACE_URL, f"legacy:{client_id}").hex
            s.execute(
                pg_insert(User)
                .values(
                    id=uid,
                    subject=client_id,
                    provider="legacy",
                    username=f"legacy:{client_id[:16]}",
                    email="",
                    display_name="Legacy user",
                    roles=[],
                    created_at=now,
                    last_seen_at=now,
                )
                .on_conflict_do_nothing(index_elements=["provider", "subject"])
            )
            user_by_client[client_id] = uid
            stats["users"] += 1
        s.flush()

        # ── conversations ─────────────────────────────────────────────────────
        for r in conversations:
            owner = user_by_client.get(r["client_id"])
            if owner is None:
                continue
            s.execute(
                pg_insert(Conversation)
                .values(
                    id=r["id"],
                    user_id=owner,
                    title=r["title"] or "New conversation",
                    pinned=False,
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                # Update rather than ignore: a re-run after the title changed
                # in SQLite should carry the change over.
                .on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "title": r["title"] or "New conversation",
                        "updated_at": r["updated_at"],
                    },
                )
            )
            stats["conversations"] += 1
        s.flush()

        # ── messages ──────────────────────────────────────────────────────────
        for r in messages:
            if r["conversation_id"] not in valid_conv_ids:
                stats["skipped_orphan_messages"] += 1
                continue
            role = r["role"]
            if role not in ("user", "assistant", "error"):
                # The Postgres CHECK constraint would reject these and abort the
                # whole transaction; skipping keeps the rest of the migration.
                stats["skipped_bad_role"] += 1
                continue

            payload = _col(r, "payload")
            if isinstance(payload, str) and payload:
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    # Keep unparseable text rather than dropping it — it is
                    # someone's answer, and a wrapper preserves it as JSONB.
                    payload = {"_unparsed": payload}
            else:
                payload = None

            s.execute(
                pg_insert(Message)
                .values(
                    id=r["id"],
                    conversation_id=r["conversation_id"],
                    role=role,
                    text=r["text"] or "",
                    has_image=bool(_col(r, "has_image", 0)),
                    payload=payload,
                    feedback=_col(r, "feedback"),
                    created_at=r["created_at"],
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            stats["messages"] += 1
        s.flush()

        # ── corrections ───────────────────────────────────────────────────────
        for r in corrections:
            owner = user_by_client.get(_col(r, "client_id"))
            if owner is None:
                # A correction whose author is unknown is still valuable: it
                # feeds future answers. Attach it to a synthetic legacy user
                # rather than dropping it.
                owner = user_by_client.setdefault(
                    "__unknown__",
                    _ensure_unknown_user(s, now),
                )
            s.execute(
                pg_insert(Correction)
                .values(
                    id=r["id"],
                    user_id=owner,
                    question=r["question"],
                    correction=r["correction"],
                    created_at=r["created_at"],
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            stats["corrections"] += 1

    src.close()
    return stats


def _ensure_unknown_user(s, now: float) -> str:
    uid = uuid.uuid5(uuid.NAMESPACE_URL, "legacy:__unknown__").hex
    s.execute(
        pg_insert(User)
        .values(
            id=uid,
            subject="__unknown__",
            provider="legacy",
            username="legacy:unknown",
            email="",
            display_name="Unknown legacy user",
            roles=[],
            created_at=now,
            last_seen_at=now,
        )
        .on_conflict_do_nothing(index_elements=["provider", "subject"])
    )
    s.flush()
    return s.execute(
        select(User.id).where(User.provider == "legacy", User.subject == "__unknown__")
    ).scalar_one()


def verify(sqlite_path: Path, db: Database) -> bool:
    """Compare both sides and explain any difference.

    Counts alone would be misleading — a migration that dropped 3 rows and
    invented 3 others has matching counts — so orphans and rejected roles are
    reported as the expected, accounted-for delta.
    """
    src = _open_sqlite(sqlite_path)
    conversations = _rows(src, "conversations")
    messages = _rows(src, "messages")
    corrections = _rows(src, "corrections")
    valid = {r["id"] for r in conversations}
    orphans = sum(1 for m in messages if m["conversation_id"] not in valid)
    bad_role = sum(
        1
        for m in messages
        if m["conversation_id"] in valid
        and m["role"] not in ("user", "assistant", "error")
    )
    src.close()

    with db.session() as s:
        pg_conv = s.execute(select(func.count()).select_from(Conversation)).scalar_one()
        pg_msg = s.execute(select(func.count()).select_from(Message)).scalar_one()
        pg_corr = s.execute(select(func.count()).select_from(Correction)).scalar_one()

    expected_msg = len(messages) - orphans - bad_role
    rows = [
        ("conversations", len(conversations), pg_conv, len(conversations)),
        ("messages", len(messages), pg_msg, expected_msg),
        ("corrections", len(corrections), pg_corr, len(corrections)),
    ]

    print(f"{'table':<16}{'sqlite':>8}{'postgres':>10}{'expected':>10}  status")
    ok = True
    for name, n_src, n_dst, expect in rows:
        good = n_dst >= expect
        ok &= good
        print(
            f"{name:<16}{n_src:>8}{n_dst:>10}{expect:>10}  "
            f"{'OK' if good else 'MISMATCH'}"
        )
    if orphans or bad_role:
        print(
            f"\nexcluded by design: {orphans} orphaned message(s), "
            f"{bad_role} with an unrecognised role"
        )
    return bool(ok)


def link_legacy(db: Database, legacy_subject: str, owner_subject: str) -> dict:
    """Hand a legacy client id's history to an authenticated user.

    Kept as an explicit, operator-run step rather than something the app infers.
    A browser UUID identifies a *browser*, not a person: guessing that whoever
    logs in next owns it would hand one person another person's conversations,
    which is precisely the failure the whole auth phase exists to prevent.

    Re-pointing the rows (rather than copying) means the history moves once and
    the legacy row is left empty, so running it twice is harmless.
    """
    with db.session() as s:
        legacy = s.execute(
            select(User).where(User.subject == legacy_subject)
        ).scalar_one_or_none()
        if legacy is None:
            raise SystemExit(f"no user with subject {legacy_subject!r}")

        owner = s.execute(
            select(User).where(User.subject == owner_subject)
        ).scalar_one_or_none()
        if owner is None:
            # The target has never signed in, so no row exists yet. Create it
            # with the subject their token will carry, and the first login
            # attaches to it.
            owner_id = uuid.uuid5(uuid.NAMESPACE_URL, f"oidc:{owner_subject}").hex
            s.execute(
                pg_insert(User)
                .values(
                    id=owner_id,
                    subject=owner_subject,
                    provider="keycloak",
                    username=owner_subject[:255],
                    roles=[],
                    created_at=time.time(),
                    last_seen_at=time.time(),
                )
                .on_conflict_do_nothing(index_elements=["provider", "subject"])
            )
            s.flush()
            owner = s.execute(
                select(User).where(User.subject == owner_subject)
            ).scalar_one()

        moved_conv = s.execute(
            Conversation.__table__.update()
            .where(Conversation.user_id == legacy.id)
            .values(user_id=owner.id)
        ).rowcount
        moved_corr = s.execute(
            Correction.__table__.update()
            .where(Correction.user_id == legacy.id)
            .values(user_id=owner.id)
        ).rowcount

    return {"conversations": moved_conv, "corrections": moved_corr}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sqlite", type=Path, default=DEFAULT_SQLITE)
    ap.add_argument("--database-url", default=None)
    ap.add_argument("--dry-run", action="store_true", help="report, change nothing")
    ap.add_argument("--verify", action="store_true", help="compare counts only")
    ap.add_argument(
        "--link-legacy",
        nargs=2,
        metavar=("LEGACY_CLIENT_ID", "OIDC_SUBJECT"),
        help=(
            "give a legacy client id's conversations to an authenticated user. "
            "Deliberately manual: a browser UUID identifies a browser, not a "
            "person, so guessing the owner could hand over someone else's chats."
        ),
    )
    ap.add_argument(
        "--list-users",
        action="store_true",
        help="show identities and how many conversations each owns",
    )
    args = ap.parse_args()

    db = Database(args.database_url) if args.database_url else Database()
    if not db.ping():
        print(f"cannot reach Postgres at {db.url}", file=sys.stderr)
        return 2

    if args.list_users:
        with db.session() as s:
            rows = s.execute(
                select(
                    User.provider,
                    User.subject,
                    User.username,
                    func.count(Conversation.id).label("n"),
                )
                .outerjoin(Conversation, Conversation.user_id == User.id)
                .group_by(User.id)
                .order_by(func.count(Conversation.id).desc())
            ).all()
        print(f"{'provider':<10}{'conversations':>14}  subject")
        for r in rows:
            print(f"{r.provider:<10}{r.n:>14}  {r.subject}")
        return 0

    if args.link_legacy:
        legacy_subject, owner_subject = args.link_legacy
        moved = link_legacy(db, legacy_subject, owner_subject)
        print(
            f"moved {moved['conversations']} conversation(s) and "
            f"{moved['corrections']} correction(s)\n"
            f"  from {legacy_subject}\n"
            f"    to {owner_subject}"
        )
        return 0

    if args.verify:
        return 0 if verify(args.sqlite, db) else 1

    db.create_all()
    stats = migrate(args.sqlite, db, dry_run=args.dry_run)

    label = "would migrate" if args.dry_run else "migrated"
    print(f"{label}:")
    for k in ("users", "conversations", "messages", "corrections"):
        print(f"  {k:<14}{stats[k]:>6}")
    if stats["skipped_orphan_messages"]:
        print(f"  skipped orphan messages: {stats['skipped_orphan_messages']}")
    if stats["skipped_bad_role"]:
        print(f"  skipped bad role:        {stats['skipped_bad_role']}")

    if args.dry_run:
        return 0

    print()
    return 0 if verify(args.sqlite, db) else 1


if __name__ == "__main__":
    raise SystemExit(main())
