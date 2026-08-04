#!/usr/bin/env python3
"""
Migrate report files from the reports/ directory into MinIO + the catalog.

    python scripts/migrate_reports_to_minio.py --dry-run
    python scripts/migrate_reports_to_minio.py
    python scripts/migrate_reports_to_minio.py --verify

Same guarantees as the chat migration, for the same reason — a migration you
cannot re-run is one you cannot fix:

* **Idempotent.** Keys are derived from filenames, so re-uploading the same
  file overwrites the same key. On a versioned bucket that adds a version
  rather than duplicating a report, and the catalog upserts on the key's hash.
  A skip-if-identical check (by SHA-256) keeps a re-run from making pointless
  versions.
* **Non-destructive.** Source files are read, never moved or deleted. Rollback
  is `STORAGE_BACKEND=filesystem`.
* **Verified.** `--verify` compares every local file against the bucket
  byte-for-byte via SHA-256, not just by count, and reports the catalog row
  count separately.

The .md sibling of each .json is carried across too: the report viewer offers
both, and migrating only the JSON would silently break markdown downloads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import func, select  # noqa: E402

from app.db.models import Report  # noqa: E402
from app.db.session import Database  # noqa: E402
from app.reports.storage_service import StorageReportService, object_key  # noqa: E402
from app.shared.storage.base import ObjectNotFoundError  # noqa: E402
from app.shared.storage.factory import get_storage  # noqa: E402

DEFAULT_REPORTS = REPO_ROOT / "reports"

CONTENT_TYPES = {".json": "application/json", ".md": "text/markdown"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _local_files(reports_dir: Path) -> list[Path]:
    return sorted(
        p
        for p in reports_dir.iterdir()
        if p.is_file() and p.suffix in (".json", ".md")
    )


def migrate(reports_dir: Path, storage, *, dry_run: bool) -> dict:
    stats = {"uploaded": 0, "unchanged": 0, "failed": 0, "bytes": 0}

    for path in _local_files(reports_dir):
        key = object_key(path.name)
        data = path.read_bytes()

        if not dry_run:
            # Skip identical content: on a versioned bucket a blind re-upload
            # would create a new version of every report on every run, which
            # makes the version history useless as an edit trail.
            try:
                if _sha(storage.get(key)) == _sha(data):
                    stats["unchanged"] += 1
                    continue
            except ObjectNotFoundError:
                pass
            except Exception:
                pass

            try:
                storage.put(
                    key,
                    data,
                    content_type=CONTENT_TYPES.get(path.suffix, "application/octet-stream"),
                    metadata={"filename": path.name},
                )
            except Exception as exc:  # noqa: BLE001 — report and continue
                print(f"  FAILED {path.name}: {exc}", file=sys.stderr)
                stats["failed"] += 1
                continue

        stats["uploaded"] += 1
        stats["bytes"] += len(data)

    return stats


def verify(reports_dir: Path, storage, db: Database | None) -> bool:
    """Byte-for-byte comparison of every local file against the bucket.

    Counts alone would accept a migration that uploaded the right number of
    wrong objects, so each file is compared by content hash.
    """
    local = _local_files(reports_dir)
    missing: list[str] = []
    mismatched: list[str] = []

    for path in local:
        key = object_key(path.name)
        try:
            remote = storage.get(key)
        except ObjectNotFoundError:
            missing.append(path.name)
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"  error reading {key}: {exc}", file=sys.stderr)
            missing.append(path.name)
            continue
        if _sha(remote) != _sha(path.read_bytes()):
            mismatched.append(path.name)

    n_json = sum(1 for p in local if p.suffix == ".json")
    print(f"local files      : {len(local)} ({n_json} json + {len(local) - n_json} md)")
    print(f"missing in bucket: {len(missing)}")
    print(f"content mismatch : {len(mismatched)}")

    if db is not None:
        with db.session() as s:
            rows = s.execute(
                select(func.count()).select_from(Report).where(Report.deleted_at.is_(None))
            ).scalar_one()
        print(f"catalog rows     : {rows} (expected {n_json})")

    for name in missing[:10]:
        print(f"  missing: {name}")
    for name in mismatched[:10]:
        print(f"  mismatch: {name}")

    return not missing and not mismatched


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument(
        "--skip-catalog",
        action="store_true",
        help="upload blobs only, do not build Postgres catalog rows",
    )
    args = ap.parse_args()

    if not args.reports_dir.is_dir():
        print(f"no reports directory at {args.reports_dir}", file=sys.stderr)
        return 2

    storage = get_storage("minio")
    if not storage.health():
        print("MinIO unreachable — is the stack up?", file=sys.stderr)
        return 2

    db: Database | None = None
    if not args.skip_catalog:
        db = Database()
        if not db.ping():
            print("Postgres unreachable; continuing without the catalog", file=sys.stderr)
            db = None

    if args.verify:
        return 0 if verify(args.reports_dir, storage, db) else 1

    stats = migrate(args.reports_dir, storage, dry_run=args.dry_run)
    label = "would upload" if args.dry_run else "uploaded"
    print(f"{label}: {stats['uploaded']} file(s), {stats['bytes'] / 1024:.0f} KiB")
    if stats["unchanged"]:
        print(f"unchanged (skipped): {stats['unchanged']}")
    if stats["failed"]:
        # Loud and non-zero: a run that uploaded most files and lost the rest
        # must not look like a success in a shell chain or CI job.
        print(f"FAILED: {stats['failed']} file(s) did not upload", file=sys.stderr)

    if args.dry_run:
        return 0
    if stats["failed"]:
        return 1

    # Build the catalog from what is now in the bucket, rather than from the
    # local files: this indexes exactly what was stored, so a partial upload
    # produces a catalog that matches reality instead of one that claims rows
    # whose blobs are missing.
    if db is not None:
        svc = StorageReportService(storage, db)
        result = svc.reconcile()
        print(f"catalog: indexed {result['indexed']}, skipped {result['skipped']}")

    print()
    return 0 if verify(args.reports_dir, storage, db) else 1


if __name__ == "__main__":
    raise SystemExit(main())
