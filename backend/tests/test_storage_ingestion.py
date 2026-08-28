"""
Storage-backed ingestion: the chatbot indexes object storage, not a directory.

The property under test is *equivalence*. The report listing reads object
storage while the chatbot read the local directory, so the two could disagree
about what the corpus was — a report saved through the UI landed in the bucket
and stayed invisible to retrieval. Pointing the chatbot at storage fixes that
only if it indexes the corpus identically; a migration that changed retrieval
would trade one bug for a worse one.

So these tests compare the two builders on the same corpus rather than
asserting either one in isolation.
"""

from __future__ import annotations

import hashlib
import json
import logging

import pytest

from app.chatbot import resolution
from app.chatbot.ingestion import (
    build_knowledge_base,
    build_knowledge_base_from_storage,
)
from app.reports.seed import seed_reports
from app.reports.storage_service import StorageReportService, object_key
from app.shared.storage.filesystem import FilesystemStorage

log = logging.getLogger("test")


def _report(incident_id: str, title: str, body: str) -> dict:
    return {
        "metadata": {
            "incident_id": incident_id,
            "title": title,
            "caller": "tester",
            "category": "Network",
            "subcategory": "VPN",
            "date": "2026-01-01",
        },
        "blocks": [{"type": "text", "title": "Summary", "content": body}],
    }


@pytest.fixture
def corpus(tmp_path):
    d = tmp_path / "reports"
    d.mkdir()
    (d / "INC0001_Tunnel drops.json").write_text(
        json.dumps(_report("INC0001", "Tunnel drops", "VPN tunnel fails after maintenance."))
    )
    (d / "INC0002_Cache stampede.json").write_text(
        json.dumps(_report("INC0002", "Cache stampede", "Redis cache stampede on cold start."))
    )
    (d / "INC0001_Tunnel drops.md").write_text("# Tunnel drops\nMirror of the JSON.")
    return d


@pytest.fixture
def storage(tmp_path, corpus):
    st = FilesystemStorage(tmp_path / "blobs")
    seed_reports(corpus, StorageReportService(st, None), st, log)
    return st


def _digest(kb) -> str:
    return hashlib.sha256("\x00".join(kb.documents).encode()).hexdigest()


# ── equivalence ───────────────────────────────────────────────────────────────


def test_storage_and_directory_produce_the_same_chunks(corpus, storage):
    """The guarantee the migration rests on: same corpus, same index."""
    assert _digest(build_knowledge_base_from_storage(storage, "reports")) == _digest(
        build_knowledge_base(corpus)
    )


def test_storage_and_directory_agree_on_metadata(corpus, storage):
    fs = build_knowledge_base(corpus)
    ob = build_knowledge_base_from_storage(storage, "reports")

    for field in ("incident_id", "title"):
        assert sorted(str(m[field]) for m in fs.metadata) == sorted(
            str(m[field]) for m in ob.metadata
        )
    assert fs.n_files == ob.n_files


def test_markdown_mirrors_are_skipped_in_both(corpus, storage):
    """Indexing a .md twin of a .json doubles the incident and loses schema."""
    ob = build_knowledge_base_from_storage(storage, "reports")
    sources = {m["source"] for m in ob.metadata}

    assert not any(s.endswith("INC0001_Tunnel drops.md") for s in sources)
    assert any(s.endswith("INC0001_Tunnel drops.json") for s in sources)


# ── what the directory build could not do ─────────────────────────────────────


def test_a_report_saved_to_storage_becomes_searchable(corpus, storage):
    """The bug in the other direction: a UI-saved report never reached the
    directory, so re-indexing could not find it."""
    svc = StorageReportService(storage, None)
    before = build_knowledge_base_from_storage(storage, "reports").n_files

    storage.put(
        object_key("INC0003_Broker restart.json"),
        json.dumps(_report("INC0003", "Broker restart", "Kafka broker restart loop.")).encode(),
        content_type="application/json",
    )

    after = build_knowledge_base_from_storage(storage, "reports")
    assert after.n_files == before + 1
    assert "INC0003" in {str(m["incident_id"]) for m in after.metadata}
    # And it is visible to the listing too — one corpus, not two.
    assert "INC0003" in {r.metadata.incident_id for r in svc.list_reports()}


def test_tombstoned_reports_are_not_indexed(corpus, storage):
    """A deleted report must leave retrieval as well as the listing."""
    svc = StorageReportService(storage, None)
    svc.delete(filename="INC0002_Cache stampede.json")

    kb = build_knowledge_base_from_storage(storage, "reports")

    assert "INC0002" not in {str(m["incident_id"]) for m in kb.metadata}


def test_empty_storage_raises_rather_than_indexing_nothing(tmp_path):
    """Same failure mode as the directory build: an empty index is a
    configuration error, not a working chatbot that answers nothing."""
    empty = FilesystemStorage(tmp_path / "empty")

    with pytest.raises(ValueError):
        build_knowledge_base_from_storage(empty, "reports")


# ── resolution ────────────────────────────────────────────────────────────────


def test_resolution_reads_full_documents_through_storage(corpus, storage):
    """Chunk `path` is an object key now; without the injected reader every
    full-document read returns "" and answers silently degrade to chunks."""
    ob = build_knowledge_base_from_storage(storage, "reports")
    chunk = next(m for m in ob.metadata if m["path"].endswith(".json"))

    resolution.set_document_reader(lambda k: storage.get(k).decode("utf-8"))
    try:
        text = resolution._full_document_text(chunk)
    finally:
        resolution.set_document_reader(None)

    assert "INC0001" in text or "INC0002" in text
    assert len(text) > len("# Tunnel drops")


def test_document_reader_swap_clears_the_cache(corpus, storage):
    """A stale cache would serve documents from the previous backend."""
    ob = build_knowledge_base_from_storage(storage, "reports")
    chunk = next(m for m in ob.metadata if m["path"].endswith(".json"))

    resolution.set_document_reader(lambda k: "FIRST")
    assert resolution._full_document_text(chunk) == ""  # not valid JSON

    resolution.set_document_reader(lambda k: storage.get(k).decode("utf-8"))
    try:
        assert resolution._full_document_text(chunk) != ""
    finally:
        resolution.set_document_reader(None)
