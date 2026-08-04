"""
reports/service.py — report CRUD over the shared reports/ directory.

This is a faithful port of the file-handling logic in the original Express
`server.ts`. It is deliberately framework-agnostic (no FastAPI imports) so the
same logic can later be pointed at a SharePoint adapter instead of the local
filesystem: swap this module's storage calls, leave the router untouched.

Behaviour preserved from server.ts:
  - incident_id sanitized to [a-z0-9_] for filenames
  - CREATE rejects a duplicate incident_id (409-equivalent DuplicateReportError)
  - UPDATE (editingFilename) deletes old json+md, rewrites under the same name
  - transaction safety: if the .md write fails, the .json write is rolled back
  - path-traversal guard on delete
  - list sorted newest-first by mtime
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from app.shared.schema import (
    IncidentReport,
    ReportListItem,
    ReportMetadata,
)


class DuplicateReportError(Exception):
    """Raised when creating a report whose incident_id already exists."""

    def __init__(self, incident_id: str):
        self.incident_id = incident_id
        super().__init__(f"An incident with id '{incident_id}' already exists")


class ReportNotFoundError(Exception):
    """Raised when a requested report file does not exist."""


class InvalidFilenameError(Exception):
    """Raised on a filename that fails the path-traversal guard."""


def _now_ms() -> int:
    return int(time.time() * 1000)


def _safe_incident_id(incident_id: str) -> str:
    """Mirror of the TS `replace(/[^a-z0-9]/gi, '_').toLowerCase()`."""
    return re.sub(r"[^a-z0-9]", "_", incident_id, flags=re.IGNORECASE).lower()


def _normalize_report(data: dict) -> dict:
    """Normalize the two on-disk report shapes to a flat {metadata, blocks}.

    Some legacy reports are saved wrapped as
    ``{"editingFilename", "markdown", "report": {"metadata", "blocks"}}`` while
    newer ones are already flat ``{"metadata", "blocks"}``. The report viewer
    reads metadata/blocks at the top level, so a wrapped file rendered blank —
    the root cause of "some sources open, others are blank". Unwrapping here at
    the API boundary fixes every consumer without touching the viewer.
    """
    if isinstance(data, dict) and "metadata" not in data and isinstance(
        data.get("report"), dict
    ):
        inner = data["report"]
        if "metadata" in inner or "blocks" in inner:
            return inner
    return data


class ReportService:
    def __init__(self, reports_dir: Path):
        self.reports_dir = reports_dir
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    # ── save / update ─────────────────────────────────────────────────────────

    def save(
        self,
        report: IncidentReport,
        markdown: str,
        editing_filename: str | None = None,
    ) -> dict:
        """Create or update a report. Returns the response payload dict.

        Raises DuplicateReportError on a create that collides with an existing
        incident_id (the router maps this to HTTP 409).
        """
        incident_id = report.metadata.incident_id or f"untitled-{_now_ms()}"
        safe_id = _safe_incident_id(incident_id)
        timestamp = _now_ms()

        is_updating = False

        if editing_filename:
            # UPDATE: reuse the existing filename, delete old pair first.
            is_updating = True
            json_filename = editing_filename
            md_filename = editing_filename.replace(".json", ".md")
            self._unlink_quiet(json_filename)
            self._unlink_quiet(md_filename)
        else:
            # CREATE: reject duplicates, then mint timestamped filenames.
            for existing in self.reports_dir.iterdir():
                name = existing.name
                if name.startswith(f"incident_{safe_id}_") and name.endswith(".json"):
                    raise DuplicateReportError(incident_id)
            json_filename = f"incident_{safe_id}_{timestamp}.json"
            md_filename = f"incident_{safe_id}_{timestamp}.md"

        json_path = self.reports_dir / json_filename
        md_path = self.reports_dir / md_filename

        # Write JSON first.
        json_path.write_text(
            json.dumps(report.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Write MD; on failure roll back the JSON to keep the pair consistent.
        try:
            md_path.write_text(markdown, encoding="utf-8")
        except OSError:
            self._unlink_quiet(json_filename)
            raise

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
        items: list[ReportListItem] = []
        for path in self.reports_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                items.append(
                    ReportListItem(
                        filename=path.name,
                        metadata=ReportMetadata(**data["metadata"]),
                        timestamp=path.stat().st_mtime * 1000,  # epoch ms
                    )
                )
            except (OSError, ValueError, KeyError):
                # Skip unreadable/malformed files, matching the TS try/continue.
                continue
        items.sort(key=lambda r: r.timestamp, reverse=True)
        return items

    def get_content(self, filename: str) -> dict:
        self._guard_filename(filename)
        path = self.reports_dir / filename
        if not path.exists():
            raise ReportNotFoundError(filename)
        return _normalize_report(json.loads(path.read_text(encoding="utf-8")))

    def resolve_path(self, filename: str) -> Path:
        """Return the on-disk path for a download, guarded against traversal."""
        self._guard_filename(filename)
        path = self.reports_dir / filename
        if not path.exists():
            raise ReportNotFoundError(filename)
        return path

    def read_bytes(self, filename: str) -> bytes:
        """Raw bytes for a download.

        Exists so the router has one code path for both services: object
        storage has no local path to hand to FileResponse, and branching in the
        handler on which service is configured would put storage knowledge back
        in the HTTP layer.
        """
        return self.resolve_path(filename).read_bytes()

    def download_url(self, filename: str, expires_in: int = 3600) -> str | None:
        """No direct URL for local files; the caller streams the bytes."""
        return None

    # ── delete ────────────────────────────────────────────────────────────────

    def delete(
        self,
        filename: str | None = None,
        incident_id: str | None = None,
    ) -> None:
        # If only incident_id is given, resolve to its latest file.
        if incident_id and not filename:
            candidates = sorted(
                p.name
                for p in self.reports_dir.glob("*.json")
                if p.name.startswith(f"incident_{incident_id}_")
            )
            if not candidates:
                raise ReportNotFoundError(incident_id)
            filename = candidates[-1]

        if not filename:
            raise InvalidFilenameError("filename or incident_id is required")

        self._guard_filename(filename)
        self._unlink_quiet(filename)
        self._unlink_quiet(filename.replace(".json", ".md"))

    # ── helpers ───────────────────────────────────────────────────────────────

    def _unlink_quiet(self, filename: str) -> None:
        try:
            (self.reports_dir / filename).unlink()
        except FileNotFoundError:
            pass

    @staticmethod
    def _guard_filename(filename: str) -> None:
        # Same guard as the TS delete handler, applied to every path-taking call.
        if ".." in filename or "/" in filename or "\\" in filename:
            raise InvalidFilenameError("Invalid filename")
