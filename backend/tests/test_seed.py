"""
Startup seeding tests.

The bug this guards against had two halves, and both are asserted here:

  1. A fresh clone has reports on disk but an empty bucket, so the chatbot
     (which indexes the directory) answered from reports the UI could not list.
     Seeding must close that gap.
  2. Seeding must never run against a populated bucket — a restart that
     resurrects a report someone deleted through the UI would be a worse bug
     than the one being fixed.

Filesystem-backed throughout: seeding talks to the `Storage` interface, so what
holds for one backend holds for the other, and these stay runnable with nothing
else up.
"""

from __future__ import annotations

import json
import logging

import pytest

from app.reports.seed import (
    bucket_is_empty,
    local_report_files,
    seed_reports,
    upload_reports,
)
from app.reports.storage_service import StorageReportService, object_key
from app.shared.storage.base import ObjectNotFoundError
from app.shared.storage.filesystem import FilesystemStorage


@pytest.fixture
def storage(tmp_path):
    return FilesystemStorage(tmp_path / "blobs")


@pytest.fixture
def service(storage):
    # No database: exercises the bucket-scan listing path, so these tests
    # assert what the blobs say rather than what a catalog claims.
    return StorageReportService(storage, None)


@pytest.fixture
def log():
    return logging.getLogger("test.seed")


def _report(incident_id: str, title: str = "Something broke") -> dict:
    """A report in the on-disk shape the real corpus uses.

    Files in reports/ are the save-request envelope
    `{editingFilename, markdown, report}`, which `_normalize_report` unwraps —
    and ReportMetadata requires caller/category/subcategory/date. Building the
    fixture any smaller would pass through the seeder but be dropped by the
    listing, which is precisely the failure these tests exist to catch.
    """
    return {
        "editingFilename": None,
        "markdown": f"# {title}",
        "report": {
            "metadata": {
                "incident_id": incident_id,
                "title": title,
                "caller": "System Generated",
                "category": "networking",
                "subcategory": "Test Subcategory",
                "date": "2026-07-05",
                "priority": "P1",
            },
            "blocks": [{"type": "text", "text": "cause and fix"}],
        },
    }


@pytest.fixture
def reports_dir(tmp_path):
    """A miniature corpus: two JSON reports and one markdown sibling."""
    d = tmp_path / "reports"
    d.mkdir()
    (d / "INC0001_First incident.json").write_text(
        json.dumps(_report("INC0001", "First incident")), encoding="utf-8"
    )
    (d / "INC0002_Second incident.json").write_text(
        json.dumps(_report("INC0002", "Second incident")), encoding="utf-8"
    )
    (d / "INC0001_First incident.md").write_text("# First incident", encoding="utf-8")
    return d


# ── the empty-bucket case (the fresh clone) ───────────────────────────────────


def test_empty_bucket_is_reported_empty(storage):
    assert bucket_is_empty(storage) is True


def test_seeding_populates_an_empty_bucket(reports_dir, service, storage, log):
    result = seed_reports(reports_dir, service, storage, log)

    assert result["seeded"] is True
    assert result["uploaded"] == 3       # 2 json + 1 md
    assert result["failed"] == 0
    assert bucket_is_empty(storage) is False


def test_seeded_reports_are_listable(reports_dir, service, storage, log):
    """The actual user-visible symptom: the UI listing was empty."""
    assert service.list_reports() == []

    seed_reports(reports_dir, service, storage, log)

    listed = {r.metadata.incident_id for r in service.list_reports()}
    assert listed == {"INC0001", "INC0002"}


def test_seeded_content_is_readable(reports_dir, service, storage, log):
    seed_reports(reports_dir, service, storage, log)

    content = service.get_content("INC0001_First incident.json")
    assert content["metadata"]["incident_id"] == "INC0001"
    assert content["blocks"]


def test_markdown_siblings_are_seeded_too(reports_dir, service, storage, log):
    """Seeding only the JSON would silently break markdown downloads."""
    seed_reports(reports_dir, service, storage, log)

    assert storage.get(object_key("INC0001_First incident.md")) == b"# First incident"


# ── the populated-bucket case (every restart after the first) ─────────────────


def test_second_run_is_a_noop(reports_dir, service, storage, log):
    seed_reports(reports_dir, service, storage, log)
    again = seed_reports(reports_dir, service, storage, log)

    assert again["seeded"] is False
    assert again["reason"] == "already_seeded"


def test_restart_does_not_resurrect_a_deleted_report(
    reports_dir, service, storage, log
):
    """The rule that makes auto-seeding safe to leave on.

    A report deleted through the UI is still present in the local reports/
    directory, so a seeder that ran unconditionally would bring it back on the
    next restart — silently undoing a deliberate deletion.
    """
    seed_reports(reports_dir, service, storage, log)
    service.delete(filename="INC0001_First incident.json")

    seed_reports(reports_dir, service, storage, log)

    remaining = {r.metadata.incident_id for r in service.list_reports()}
    assert remaining == {"INC0002"}
    with pytest.raises(ObjectNotFoundError):
        storage.get(object_key("INC0001_First incident.json"))


def test_edits_in_the_bucket_survive_a_restart(reports_dir, service, storage, log):
    """The bucket is the source of truth once populated, not the directory."""
    seed_reports(reports_dir, service, storage, log)
    edited = _report("INC0001", "Edited in the app")
    storage.put(
        object_key("INC0001_First incident.json"),
        json.dumps(edited).encode("utf-8"),
        content_type="application/json",
    )

    seed_reports(reports_dir, service, storage, log)

    content = service.get_content("INC0001_First incident.json")
    assert content["metadata"]["title"] == "Edited in the app"


# ── degradation ───────────────────────────────────────────────────────────────


def test_missing_reports_dir_is_not_fatal(tmp_path, service, storage, log):
    result = seed_reports(tmp_path / "nope", service, storage, log)

    assert result == {"seeded": False, "reason": "no_reports_dir"}


def test_empty_reports_dir_is_not_fatal(tmp_path, service, storage, log):
    empty = tmp_path / "empty"
    empty.mkdir()

    result = seed_reports(empty, service, storage, log)

    assert result == {"seeded": False, "reason": "no_local_files"}


def test_unreadable_storage_is_treated_as_populated(reports_dir, service, log):
    """`bucket_is_empty` must not guess "empty" when storage is misbehaving:
    seeding on top of a bucket whose contents are unknown is the worse error."""

    class BrokenStorage:
        def list(self, prefix=""):
            raise RuntimeError("storage down")

        def exists(self, key):
            raise RuntimeError("storage down")

    broken = BrokenStorage()
    assert bucket_is_empty(broken) is False
    assert seed_reports(reports_dir, service, broken, log)["seeded"] is False


def test_upload_failure_is_counted_not_raised(reports_dir, storage, monkeypatch):
    """One bad object must not abort the whole seed."""

    def explode(key, *a, **kw):
        if key.endswith(".md"):
            raise RuntimeError("nope")
        return storage.__class__.put(storage, key, *a, **kw)

    monkeypatch.setattr(storage, "put", explode)
    stats = upload_reports(reports_dir, storage)

    assert stats["uploaded"] == 2
    assert stats["failed"] == 1
    assert len(stats["errors"]) == 1


# ── idempotence of the uploader itself ────────────────────────────────────────


def test_reupload_skips_identical_content(reports_dir, storage):
    """Blind re-uploads would add a version per report per run on a versioned
    bucket, making the version history useless as an edit trail."""
    first = upload_reports(reports_dir, storage)
    second = upload_reports(reports_dir, storage)

    assert first["uploaded"] == 3
    assert second["uploaded"] == 0
    assert second["unchanged"] == 3


def test_local_report_files_ignores_other_extensions(reports_dir):
    (reports_dir / "notes.txt").write_text("ignore me", encoding="utf-8")
    (reports_dir / ".DS_Store").write_text("junk", encoding="utf-8")

    names = {p.name for p in local_report_files(reports_dir)}

    assert names == {
        "INC0001_First incident.json",
        "INC0002_Second incident.json",
        "INC0001_First incident.md",
    }


# ── filesystem listing parity ─────────────────────────────────────────────────


def test_filesystem_lists_wrapped_reports(reports_dir):
    """The filesystem service must list the wrapped shape too.

    `list_reports` read `data["metadata"]` raw while `get_content` normalized,
    so a wrapped report opened fine when clicked but never appeared in the
    listing — it raised KeyError into the skip-malformed `continue`. On the real
    corpus that hid 60 of 69 reports, which looks exactly like an empty bucket.
    """
    from app.reports.service import ReportService

    listed = {r.metadata.incident_id for r in ReportService(reports_dir).list_reports()}

    assert listed == {"INC0001", "INC0002"}


# ── the partially-populated bucket (the teammate's case) ──────────────────────


def test_corpus_is_seeded_into_a_bucket_holding_a_user_report(
    reports_dir, service, storage, log
):
    """The regression this rewrite exists for.

    Someone who ran the app before startup seeding existed, and saved one
    report, had a non-empty bucket. The old empty-bucket gate then skipped
    seeding on every subsequent boot, so they saw their own report and none of
    the corpus — while the chatbot, which reads the directory, answered from
    all of it.
    """
    storage.put(
        object_key("incident_mine_1.json"),
        b'{"metadata": {"incident_id": "MINE"}, "blocks": []}',
        content_type="application/json",
    )
    assert bucket_is_empty(storage) is False

    result = seed_reports(reports_dir, service, storage, log)

    assert result["seeded"] is True
    listed = {r.metadata.incident_id for r in service.list_reports()}
    assert {"INC0001", "INC0002"} <= listed


def test_seeding_does_not_overwrite_a_user_report(reports_dir, service, storage, log):
    """A report the user created is not in reports_dir, so it must survive."""
    mine = object_key("incident_mine_1.json")
    storage.put(mine, b'{"metadata": {"incident_id": "MINE"}, "blocks": []}',
                content_type="application/json")

    seed_reports(reports_dir, service, storage, log)

    assert storage.get(mine) == b'{"metadata": {"incident_id": "MINE"}, "blocks": []}'


def test_only_missing_files_are_uploaded(reports_dir, service, storage, log):
    """A boot with most of the corpus present writes only the gap."""
    seed_reports(reports_dir, service, storage, log)
    storage.delete(object_key("INC0002_Second incident.json"))

    result = seed_reports(reports_dir, service, storage, log)

    assert result["seeded"] is True
    assert result["uploaded"] == 1


def test_a_deleted_report_is_not_resurrected(reports_dir, service, storage, log, monkeypatch):
    """Per-file seeding must not undo a deletion.

    This is the property the old empty-bucket gate protected by accident. It is
    now explicit: the catalog records the deleted key, and the seeder skips it.
    """
    seed_reports(reports_dir, service, storage, log)
    gone = object_key("INC0002_Second incident.json")
    storage.delete(gone)

    monkeypatch.setattr(
        "app.reports.seed._soft_deleted_keys", lambda service: {gone}
    )

    result = seed_reports(reports_dir, service, storage, log)

    assert result["seeded"] is False
    assert not storage.exists(gone)
