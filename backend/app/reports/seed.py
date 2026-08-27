"""
reports/seed.py — put the tracked reports/ corpus into an empty bucket.

The reports in `reports/` are tracked in git, so every clone has them on disk.
The chatbot indexes that directory directly, but the report *listing* reads
object storage — so on a fresh checkout the two disagreed: the chatbot answered
from all 91 reports while the UI showed an empty list, because nothing ever
copied the files into MinIO. `scripts/migrate_reports_to_minio.py` did it, but
only when someone remembered to run it.

Seeding on startup closes that gap. The rule is deliberately narrow:

* **Only when the bucket is empty.** A populated bucket is the source of truth
  and is left alone — reports deleted through the UI must not reappear on the
  next restart, which is exactly what re-seeding a live bucket would do.
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

from .storage_service import KEY_PREFIX, object_key

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
) -> dict:
    """Upload every report file into `storage`. Idempotent.

    Keys are derived from filenames, so re-uploading the same file overwrites
    the same key. `skip_identical` compares content first, which keeps a re-run
    from making a new version of every report on a versioned bucket and
    rendering the version history useless as an edit trail.
    """
    stats: dict = {"uploaded": 0, "unchanged": 0, "failed": 0, "bytes": 0, "errors": []}

    for path in local_report_files(reports_dir):
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


def seed_if_empty(reports_dir: Path, service, storage: Storage, log) -> dict:
    """Seed an empty bucket from `reports_dir`, then rebuild the catalog.

    Returns a stats dict; `{"seeded": False}` when nothing was done, which is
    the normal case on every restart after the first.
    """
    if not reports_dir.is_dir():
        log.info(
            "no reports directory at %s; nothing to seed", reports_dir,
            extra={"event": "seed_skipped", "reason": "no_reports_dir"},
        )
        return {"seeded": False, "reason": "no_reports_dir"}

    if not bucket_is_empty(storage):
        return {"seeded": False, "reason": "bucket_not_empty"}

    files = local_report_files(reports_dir)
    if not files:
        return {"seeded": False, "reason": "no_local_files"}

    log.info(
        "report bucket is empty; seeding %d file(s) from %s",
        len(files), reports_dir,
        extra={"event": "seed_start", "files": len(files)},
    )

    stats = upload_reports(reports_dir, storage)

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

    return {"seeded": True, "indexed": indexed, **stats}