"""
reports/seed.py — put the tracked reports/ corpus into the bucket.

The reports in `reports/` are tracked in git, so every clone has them on disk.
The chatbot indexes that directory directly, but the report *listing* reads
object storage — so on a fresh checkout the two disagreed: the chatbot answered
from all 91 reports while the UI showed an empty list, because nothing ever
copied the files into MinIO. `scripts/migrate_reports_to_minio.py` did it, but
only when someone remembered to run it.

Seeding on startup closes that gap. The rule is per *file*:

* **Upload what is missing.** Any corpus file whose key is absent is uploaded,
  so a bucket holding only a user's own report — the state anyone who ran the
  app before this code existed is in — still gets the corpus. Keys the catalog
  marks deleted are skipped, so a report someone removed through the UI stays
  removed across restarts.
* **Blobs only.** The catalog is rebuilt by `StorageReportService.reconcile()`
  afterwards, from what actually landed in the bucket, so a partial upload
  produces a catalog matching reality rather than rows pointing at absent blobs.
* **Never fatal.** A seed failure leaves the app serving an empty list, which is
  recoverable by running the migration script. Refusing to boot would not be.

Shared with `scripts/migrate_reports_to_minio.py` so there is one implementation
of "put these files in the bucket" rather than two that can drift.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.shared.storage.base import ObjectNotFoundError, Storage

from .storage_service import KEY_PREFIX, _tombstone_key, object_key

# The only extensions the corpus contains. The .md sibling of each .json is
# carried across too: the viewer offers both, and seeding only the JSON would
# silently break markdown downloads.
CONTENT_TYPES = {".json": "application/json", ".md": "text/markdown"}


def local_report_files(reports_dir: Path) -> list[Path]:
    """Every report file in `reports_dir`, in a stable order."""
    return sorted(
        p for p in reports_dir.iterdir() if p.is_file() and p.suffix in CONTENT_TYPES
    )


def bucket_is_empty(storage: Storage) -> bool:
    """True if no report blob exists yet.

    An error is reported as *not* empty. Seeding on a storage backend that is
    misbehaving is the more damaging guess of the two.
    """
    try:
        return not any(o.key.endswith(".json") for o in storage.list(KEY_PREFIX))
    except Exception:
        return False


def upload_reports(
    reports_dir: Path,
    storage: Storage,
    *,
    dry_run: bool = False,
    skip_identical: bool = True,
    only: list[Path] | None = None,
) -> dict:
    """Upload report files into `storage`. Idempotent.

    Keys are derived from filenames, so re-uploading the same file overwrites
    the same key. `skip_identical` compares content first, which keeps a re-run
    from making a new version of every report on a versioned bucket and
    rendering the version history useless as an edit trail.

    `only` restricts the upload to a caller-chosen subset — the startup seeder
    passes the files it found missing, so a boot with 68 of 69 present writes
    one object instead of re-hashing the whole corpus. Defaults to everything,
    which is what the migration script wants.
    """
    stats: dict = {"uploaded": 0, "unchanged": 0, "failed": 0, "bytes": 0, "errors": []}

    for path in (local_report_files(reports_dir) if only is None else only):
        key = object_key(path.name)
        data = path.read_bytes()

        if not dry_run:
            if skip_identical:
                try:
                    remote = storage.get(key)
                    if (
                        hashlib.sha256(remote).hexdigest()
                        == hashlib.sha256(data).hexdigest()
                    ):
                        stats["unchanged"] += 1
                        continue
                except ObjectNotFoundError:
                    pass
                except Exception:
                    # Unreadable existing object: fall through and overwrite it.
                    pass

            try:
                storage.put(
                    key,
                    data,
                    content_type=CONTENT_TYPES.get(
                        path.suffix, "application/octet-stream"
                    ),
                    metadata={"filename": path.name},
                )
            except Exception as exc:  # noqa: BLE001 — record and continue
                stats["failed"] += 1
                stats["errors"].append(f"{path.name}: {exc}")
                continue

        stats["uploaded"] += 1
        stats["bytes"] += len(data)

    return stats


def _soft_deleted_keys(service) -> set[str]:
    """Object keys a user deleted through the UI.

    Seeding must not resurrect them. The catalog is the only place that
    records the intent — the blob is gone from the bucket, so absence alone is
    indistinguishable from "never seeded". Without this check, per-file
    seeding would restore a deleted report on the next restart, which is worse
    than the bug it fixes.

    A catalog that cannot be read yields an empty set: the caller then seeds
    normally, which is the same behaviour as running with no Postgres at all.
    """
    db = getattr(service, "db", None)
    if db is None:
        return set()
    try:
        from sqlalchemy import select

        from app.db.models import Report

        with db.session() as s:
            rows = s.execute(
                select(Report.object_key).where(Report.deleted_at.is_not(None))
            ).scalars().all()
        return set(rows)
    except Exception:
        return set()


def _tombstoned_keys(storage: Storage, files: list[Path]) -> set[str]:
    """Keys with a deletion marker in the bucket.

    The catalog covers the Postgres configuration; this covers every other one,
    including the filesystem backend the tests and a bare `uvicorn` run use.
    Probed per candidate rather than listed, so the check costs nothing on a
    bucket that has never had a deletion.
    """
    found: set[str] = set()
    for path in files:
        key = object_key(path.name)
        try:
            if storage.exists(_tombstone_key(path.name)):
                found.add(key)
        except Exception:
            continue
    return found


def seed_reports(reports_dir: Path, service, storage: Storage, log) -> dict:
    """Upload any corpus file the bucket is missing, then rebuild the catalog.

    Per *file*, not per bucket. An earlier version seeded only when the bucket
    was completely empty, which meant anyone who ran the app once before
    pulling this code — creating a single report, so the bucket was no longer
    empty — never got the corpus at all, and saw an empty report list next to
    a chatbot answering from all 69 reports.

    The empty-bucket gate existed to stop restarts resurrecting deleted
    reports. That property is kept, more precisely: keys the catalog marks
    deleted are skipped explicitly, so only genuinely-absent files are
    uploaded. Reports a user created are never touched — they are not in
    `reports_dir`.
    """
    if not reports_dir.is_dir():
        log.info(
            "no reports directory at %s; nothing to seed", reports_dir,
            extra={"event": "seed_skipped", "reason": "no_reports_dir"},
        )
        return {"seeded": False, "reason": "no_reports_dir"}

    files = local_report_files(reports_dir)
    if not files:
        return {"seeded": False, "reason": "no_local_files"}

    deleted = _soft_deleted_keys(service) | _tombstoned_keys(storage, files)

    missing: list[Path] = []
    for path in files:
        key = object_key(path.name)
        if key in deleted:
            continue
        try:
            if not storage.exists(key):
                missing.append(path)
        except Exception:
            # Treat an unreadable probe as present: re-uploading on a flaky
            # backend is the more damaging guess.
            continue

    if not missing:
        return {"seeded": False, "reason": "already_seeded", "skipped_deleted": len(deleted)}

    log.info(
        "seeding %d missing report file(s) from %s (%d already present, "
        "%d skipped as deleted)",
        len(missing), reports_dir, len(files) - len(missing) - len(deleted),
        len(deleted),
        extra={"event": "seed_start", "files": len(missing)},
    )

    stats = upload_reports(reports_dir, storage, only=missing)

    # Catalog from the bucket, not from the local files: this indexes exactly
    # what was stored, so a partial upload yields a catalog that matches
    # reality instead of one claiming rows whose blobs are missing.
    indexed = 0
    try:
        result = service.reconcile()
        indexed = result.get("indexed", 0)
    except Exception as exc:  # noqa: BLE001
        log.error(
            "seeded blobs but failed to build the catalog (%s); listing falls "
            "back to scanning the bucket", exc,
            exc_info=True, extra={"event": "seed_reconcile_failed"},
        )

    for err in stats["errors"][:5]:
        log.error("seed upload failed: %s", err, extra={"event": "seed_upload_failed"})

    log.info(
        "seeded %d file(s), %d KiB; catalog indexed %d",
        stats["uploaded"], stats["bytes"] // 1024, indexed,
        extra={
            "event": "seed_done",
            "uploaded": stats["uploaded"],
            "failed": stats["failed"],
            "indexed": indexed,
        },
    )

    return {"seeded": True, "indexed": indexed, "skipped_deleted": len(deleted), **stats}
