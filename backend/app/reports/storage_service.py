"""
reports/storage_service.py — reports on object storage with a Postgres catalog.

Same public surface as the filesystem `ReportService`: `save`, `list_reports`,
`get_content`, `delete`, plus `resolve_path`'s replacement `read_bytes`. The
router keeps calling the same methods, so blobs moving into MinIO is invisible
to the frontend and to the chatbot's ingestion.

**Filenames stay the identity.** `incident_<slug>_<timestamp>.json` is embedded
in stored answers, source citations and the frontend's URLs, so the object key
is derived from the filename rather than replacing it. Changing that identity
would orphan every citation already saved in chat history.

**Blob is the content, catalog is the index.** The blob in MinIO is the source
of truth for what a report *says*; the Postgres row is the source of truth for
finding it. Listing is a single indexed query instead of the filesystem
version's directory scan plus a JSON parse per file.

The catalog is a cache that can be rebuilt: `reconcile()` walks the bucket and
restores rows from the blobs. That is what keeps a catalog write failing after
a blob write from losing data — the report is still there, and reconcile finds
it.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import Report
from app.db.session import Database
from app.reports.service import (
    DuplicateReportError,
    InvalidFilenameError,
    ReportNotFoundError,
    _normalize_report,
    _safe_incident_id,
)
from app.shared.schema import IncidentReport, ReportListItem, ReportMetadata
from app.shared.storage.base import ObjectNotFoundError, Storage

# Object layout. Grouping by slug keeps every artifact for one incident under a
# single prefix, so `list(prefix)` is the natural "everything about INC-42".
KEY_PREFIX = "reports"

# Two naming conventions exist in the corpus and both must round-trip:
#   generated  incident_<slug>_<epoch_ms>.json   (written by the app)
#   authored   INC0012001_Some description.json  (the bulk of the real corpus)
_GENERATED_RE = re.compile(r"^incident_(?P<slug>[a-z0-9_]+)_(?P<ts>\d+)\.(json|md)$")
_AUTHORED_RE = re.compile(r"^(?P<slug>[A-Za-z0-9-]+)_.*\.(json|md)$")


def _now_ms() -> int:
    return int(time.time() * 1000)


def object_key(filename: str) -> str:
    """Map a report filename onto its object key.

    The grouping prefix is derived from the incident id so every artifact for
    one incident shares a prefix, but **the filename is preserved verbatim** —
    it is the identity the API, the frontend URLs and stored chat citations all
    use, so rewriting it would orphan existing references.

    Anything matching neither convention goes under `_loose/` rather than being
    rejected: the filesystem service accepted any name, and refusing one here
    would make the migration lossy.
    """
    m = _GENERATED_RE.match(filename)
    if m:
        return f"{KEY_PREFIX}/{m.group('slug')}/{filename}"
    m = _AUTHORED_RE.match(filename)
    if m:
        return f"{KEY_PREFIX}/{m.group('slug').lower()}/{filename}"
    return f"{KEY_PREFIX}/_loose/{filename}"


class StorageReportService:
    def __init__(self, storage: Storage, database: Database | None = None):
        self.storage = storage
        self.db = database

    # ── save / update ─────────────────────────────────────────────────────────

    def save(
        self,
        report: IncidentReport,
        markdown: str,
        editing_filename: str | None = None,
    ) -> dict:
        incident_id = report.metadata.incident_id or f"untitled-{_now_ms()}"
        safe_id = _safe_incident_id(incident_id)
        timestamp = _now_ms()
        is_updating = False

        if editing_filename:
            self._guard_filename(editing_filename)
            is_updating = True
            json_filename = editing_filename
            md_filename = editing_filename.replace(".json", ".md")
        else:
            # Duplicate detection is a catalog lookup when one is available and
            # a prefix listing otherwise — same rule, cheaper question.
            if self._incident_exists(safe_id):
                raise DuplicateReportError(incident_id)
            json_filename = f"incident_{safe_id}_{timestamp}.json"
            md_filename = f"incident_{safe_id}_{timestamp}.md"

        json_key = object_key(json_filename)
        md_key = object_key(md_filename)

        payload = json.dumps(report.model_dump(), indent=2, ensure_ascii=False)
        body = payload.encode("utf-8")

        stored = self.storage.put(
            json_key,
            body,
            content_type="application/json",
            metadata={"incident_id": incident_id, "filename": json_filename},
        )

        # Markdown second. On a versioned bucket the failed pair is recoverable
        # (the previous version is still addressable), so unlike the filesystem
        # version there is no hand-rolled rollback that can itself fail.
        try:
            self.storage.put(
                md_key,
                markdown.encode("utf-8"),
                content_type="text/markdown",
                metadata={"incident_id": incident_id},
            )
        except Exception:
            self.storage.delete(json_key)
            raise

        self._upsert_catalog(
            report=report,
            filename=json_filename,
            key=json_key,
            version_id=stored.version_id,
            size=len(body),
            checksum=hashlib.sha256(body).hexdigest(),
        )

        return {
            "success": True,
            "isUpdating": is_updating,
            "jsonUrl": f"/api/reports/download/{json_filename}",
            "mdUrl": f"/api/reports/download/{md_filename}",
            "jsonFilename": json_filename,
            "mdFilename": md_filename,
        }

    # ── list / read ───────────────────────────────────────────────────────────

    def list_reports(self) -> list[ReportListItem]:
        """Catalog query when Postgres is available, bucket scan otherwise.

        The fallback matters: it is what makes the catalog a cache rather than
        a second source of truth that can disagree with the blobs.
        """
        if self.db is not None:
            try:
                return self._list_from_catalog()
            except Exception:
                pass
        return self._list_from_storage()

    def _list_from_catalog(self) -> list[ReportListItem]:
        with self.db.session() as s:
            rows = s.execute(
                select(Report)
                .where(Report.deleted_at.is_(None))
                .order_by(Report.updated_at.desc())
            ).scalars().all()
        items = []
        for r in rows:
            try:
                items.append(
                    ReportListItem(
                        filename=r.object_key.rsplit("/", 1)[-1],
                        metadata=ReportMetadata(**r.report_metadata),
                        timestamp=r.updated_at * 1000,
                    )
                )
            except (TypeError, ValueError):
                continue
        return items

    def _list_from_storage(self) -> list[ReportListItem]:
        items: list[ReportListItem] = []
        for obj in self.storage.list(KEY_PREFIX):
            if not obj.key.endswith(".json"):
                continue
            try:
                data = json.loads(self.storage.get(obj.key))
                data = _normalize_report(data)
                items.append(
                    ReportListItem(
                        filename=obj.key.rsplit("/", 1)[-1],
                        metadata=ReportMetadata(**data["metadata"]),
                        timestamp=obj.last_modified * 1000,
                    )
                )
            except Exception:
                # Same tolerance as the filesystem version: a malformed report
                # is skipped, not fatal to the whole listing.
                continue
        items.sort(key=lambda r: r.timestamp, reverse=True)
        return items

    def get_content(self, filename: str) -> dict:
        self._guard_filename(filename)
        try:
            raw = self.storage.get(object_key(filename))
        except ObjectNotFoundError as exc:
            raise ReportNotFoundError(filename) from exc
        return _normalize_report(json.loads(raw))

    def read_bytes(self, filename: str) -> bytes:
        """Raw blob for a download. Replaces `resolve_path`, which cannot exist
        when the bytes are not on a local disk."""
        self._guard_filename(filename)
        try:
            return self.storage.get(object_key(filename))
        except ObjectNotFoundError as exc:
            raise ReportNotFoundError(filename) from exc

    def download_url(self, filename: str, expires_in: int = 3600) -> str | None:
        """Presigned URL if the backend offers one, else None so the caller
        streams through the API instead."""
        self._guard_filename(filename)
        return self.storage.presigned_url(object_key(filename), expires_in)

    # ── delete ────────────────────────────────────────────────────────────────

    def delete(
        self, filename: str | None = None, incident_id: str | None = None
    ) -> None:
        if incident_id and not filename:
            filename = self._latest_filename_for(incident_id)
            if not filename:
                raise ReportNotFoundError(incident_id)

        if not filename:
            raise InvalidFilenameError("filename or incident_id is required")

        self._guard_filename(filename)
        self.storage.delete(object_key(filename))
        self.storage.delete(object_key(filename.replace(".json", ".md")))

        # Soft delete: the partial unique index frees the incident_id for reuse
        # while the row (and the versioned blob) remain for audit.
        if self.db is not None:
            with self.db.session() as s:
                s.execute(
                    Report.__table__.update()
                    .where(
                        Report.object_key == object_key(filename),
                        Report.deleted_at.is_(None),
                    )
                    .values(deleted_at=time.time())
                )

    # ── catalog maintenance ───────────────────────────────────────────────────

    def reconcile(self) -> dict:
        """Rebuild catalog rows from the blobs in storage.

        The recovery path for a catalog that fell behind — a failed write, a
        restored bucket, or a database restored from an older backup.
        """
        if self.db is None:
            return {"indexed": 0, "skipped": 0, "reason": "no database"}

        indexed = skipped = 0
        for obj in self.storage.list(KEY_PREFIX):
            if not obj.key.endswith(".json"):
                continue
            try:
                raw = self.storage.get(obj.key)
                data = _normalize_report(json.loads(raw))
                # Validate the metadata only, not the whole report.
                #
                # 16 reports in the real corpus have a malformed block (a code
                # block missing `items`). Requiring a full IncidentReport here
                # would drop them from the catalog entirely, making them
                # invisible in the UI — even though the filesystem service
                # listed them fine, because listing only ever needed metadata.
                # The blob stays the source of truth for content; a bad block
                # is the report viewer's problem, not a reason to lose the row.
                meta = ReportMetadata(**data["metadata"])
            except Exception:
                skipped += 1
                continue
            self._upsert_catalog_meta(
                metadata=meta,
                key=obj.key,
                version_id=obj.version_id,
                size=obj.size or len(raw),
                checksum=hashlib.sha256(raw).hexdigest(),
            )
            indexed += 1
        return {"indexed": indexed, "skipped": skipped}

    # ── helpers ───────────────────────────────────────────────────────────────

    def _upsert_catalog(
        self,
        *,
        report: IncidentReport,
        filename: str,
        key: str,
        version_id: str | None,
        size: int,
        checksum: str,
    ) -> None:
        """Catalog a validated report (the save path)."""
        self._upsert_catalog_meta(
            metadata=report.metadata,
            key=key,
            version_id=version_id,
            size=size,
            checksum=checksum,
            fallback_incident_id=filename,
        )

    def _upsert_catalog_meta(
        self,
        *,
        metadata: ReportMetadata,
        key: str,
        version_id: str | None,
        size: int,
        checksum: str,
        fallback_incident_id: str | None = None,
    ) -> None:
        """Write the catalog row from metadata alone.

        Metadata is all the catalog stores, so indexing does not require the
        report's blocks to validate — see the note in reconcile().
        """
        if self.db is None:
            return

        meta = metadata
        meta_dict: dict[str, Any] = meta.model_dump()
        incident_id = (
            meta.incident_id
            or fallback_incident_id
            or key.rsplit("/", 1)[-1]
        )
        now = time.time()

        try:
            with self.db.session() as s:
                s.execute(
                    pg_insert(Report)
                    .values(
                        id=hashlib.sha1(key.encode()).hexdigest(),
                        incident_id=incident_id,
                        slug=_safe_incident_id(incident_id),
                        title=getattr(meta, "title", "") or "",
                        severity=str(meta_dict.get("severity", "") or ""),
                        status=str(meta_dict.get("status", "") or ""),
                        author=str(meta_dict.get("author", "") or ""),
                        report_metadata=meta_dict,
                        object_key=key,
                        version_id=version_id,
                        size_bytes=size,
                        checksum=checksum,
                        created_at=now,
                        updated_at=now,
                    )
                    .on_conflict_do_update(
                        index_elements=["id"],
                        set_={
                            "incident_id": incident_id,
                            "title": getattr(meta, "title", "") or "",
                            "report_metadata": meta_dict,
                            "version_id": version_id,
                            "size_bytes": size,
                            "checksum": checksum,
                            "updated_at": now,
                            # A re-save of a soft-deleted report revives it.
                            "deleted_at": None,
                        },
                    )
                )
        except Exception:
            # The blob is written and is the source of truth; a catalog miss is
            # recoverable via reconcile(). Failing the request here would tell
            # the user their report was lost when it was not.
            pass

    def _incident_exists(self, safe_id: str) -> bool:
        if self.db is not None:
            try:
                with self.db.session() as s:
                    found = s.execute(
                        select(Report.id).where(
                            Report.slug == safe_id, Report.deleted_at.is_(None)
                        )
                    ).first()
                return found is not None
            except Exception:
                pass
        return any(
            o.key.endswith(".json")
            for o in self.storage.list(f"{KEY_PREFIX}/{safe_id}/")
        )

    def _latest_filename_for(self, incident_id: str) -> str | None:
        safe = _safe_incident_id(incident_id)
        names = sorted(
            o.key.rsplit("/", 1)[-1]
            for o in self.storage.list(f"{KEY_PREFIX}/{safe}/")
            if o.key.endswith(".json")
        )
        return names[-1] if names else None

    @staticmethod
    def _guard_filename(filename: str) -> None:
        if ".." in filename or "/" in filename or "\\" in filename:
            raise InvalidFilenameError("Invalid filename")
