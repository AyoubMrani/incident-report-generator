"""
Storage backend tests.

Parametrised over both implementations, because the value of the abstraction is
that a caller cannot tell them apart. Anything asserted here is a promise the
report service is allowed to rely on regardless of STORAGE_BACKEND.

MinIO tests skip when nothing is listening, so the suite still runs with only
the filesystem backend available.
"""

from __future__ import annotations

import os
import uuid

import pytest

from app.shared.storage.base import (
    InvalidKeyError,
    ObjectNotFoundError,
    validate_key,
)
from app.shared.storage.factory import get_storage
from app.shared.storage.filesystem import FilesystemStorage


@pytest.fixture
def fs_storage(tmp_path):
    return FilesystemStorage(tmp_path / "blobs")


@pytest.fixture
def minio_storage():
    os.environ.setdefault("MINIO_ENDPOINT", "http://localhost:9000")
    try:
        from app.shared.storage.minio import MinioStorage

        store = MinioStorage(bucket=os.environ.get("REPORTS_BUCKET", "ntt-reports"))
        if not store.health():
            pytest.skip("MinIO not reachable")
        return store
    except Exception as exc:  # noqa: BLE001 — availability probe
        pytest.skip(f"MinIO unavailable: {exc}")


@pytest.fixture(params=["filesystem", "minio"])
def storage(request, fs_storage):
    if request.param == "filesystem":
        return fs_storage
    return request.getfixturevalue("minio_storage")


@pytest.fixture
def key():
    """Unique per test — MinIO is a shared, persistent bucket."""
    return f"tests/{uuid.uuid4().hex}/report.json"


# ── round trip ────────────────────────────────────────────────────────────────


def test_put_then_get(storage, key):
    stored = storage.put(key, b'{"a": 1}', content_type="application/json")
    assert stored.key == key
    assert stored.size == 8
    assert storage.get(key) == b'{"a": 1}'


def test_put_overwrites(storage, key):
    storage.put(key, b"first")
    storage.put(key, b"second")
    assert storage.get(key) == b"second"


def test_exists_reflects_writes_and_deletes(storage, key):
    assert storage.exists(key) is False
    storage.put(key, b"x")
    assert storage.exists(key) is True
    assert storage.delete(key) is True
    assert storage.exists(key) is False


def test_delete_missing_key_reports_false(storage, key):
    assert storage.delete(key) is False


def test_get_missing_key_raises(storage, key):
    with pytest.raises(ObjectNotFoundError):
        storage.get(key)


def test_unicode_survives_round_trip(storage, key):
    """Report bodies carry accented text; a header-safe encoding step for
    metadata must not touch the payload itself."""
    body = "café — naïve — 日本語".encode()
    storage.put(key, body, metadata={"title": "café ☕"})
    assert storage.get(key) == body


def test_list_finds_written_keys(storage):
    prefix = f"tests/{uuid.uuid4().hex}"
    storage.put(f"{prefix}/a.json", b"a")
    storage.put(f"{prefix}/b.json", b"b")
    keys = {o.key for o in storage.list(prefix)}
    assert keys == {f"{prefix}/a.json", f"{prefix}/b.json"}


def test_list_of_absent_prefix_is_empty(storage):
    assert storage.list(f"tests/{uuid.uuid4().hex}/nothing") == []


# ── key safety ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "../escape", "reports/../../etc/passwd", "/absolute", "back\\slash",
     "control\x00char", "bell\x07here"],
)
def test_invalid_keys_rejected(bad):
    with pytest.raises(InvalidKeyError):
        validate_key(bad)


@pytest.mark.parametrize(
    "good",
    [
        # The real corpus: spaces are the norm, not the exception.
        "reports/inc0012001/INC0012001_VPN clients unable to establish tunnel.json",
        "reports/inc42/incident_inc42_1712345678901.json",
        "reports/_loose/café — naïve.md",
        "reports/x/parens (1) and [brackets].json",
        "reports/x/100% done + more.md",
    ],
)
def test_real_world_keys_accepted(good):
    """Regression: an earlier rule allowed only [A-Za-z0-9._/-], which rejected
    80 of the 93 real report files and made the migration silently lossy."""
    assert validate_key(good) == good


def test_key_with_spaces_round_trips(storage):
    """Spaces must survive put/get/list on both backends, not just validation."""
    key = f"tests/{uuid.uuid4().hex}/INC0012001_VPN clients unable to connect.json"
    storage.put(key, b'{"ok": true}')
    assert storage.get(key) == b'{"ok": true}'
    assert key in {o.key for o in storage.list(key.rsplit("/", 1)[0])}


@pytest.mark.parametrize("bad", ["../escape.json", "/etc/passwd"])
def test_backends_refuse_traversal(storage, bad):
    """Both backends must refuse the same keys.

    On the filesystem this prevents a real escape; on MinIO such a key would
    be accepted by S3 semantics, so refusing it keeps the two interchangeable.
    """
    with pytest.raises((InvalidKeyError, ObjectNotFoundError)):
        storage.put(bad, b"x")


# ── behaviour that legitimately differs ───────────────────────────────────────


def test_filesystem_has_no_presigned_url(fs_storage, key):
    fs_storage.put(key, b"x")
    assert fs_storage.presigned_url(key) is None


def test_minio_presigned_url_is_fetchable(minio_storage, key):
    """A presigned URL must actually work — generating a well-formed URL that
    401s would pass a weaker assertion."""
    import urllib.request

    minio_storage.put(key, b"downloadable")
    url = minio_storage.presigned_url(key, expires_in=60)
    assert url and url.startswith("http")
    with urllib.request.urlopen(url, timeout=10) as resp:
        assert resp.read() == b"downloadable"


def test_minio_keeps_versions(minio_storage, key):
    """Bucket versioning is what makes an edited report auditable."""
    minio_storage.put(key, b"v1")
    minio_storage.put(key, b"v2")
    versions = minio_storage.list_versions(key)
    assert len(versions) >= 2
    oldest = versions[-1]
    assert minio_storage.get(key, version_id=oldest.version_id) == b"v1"
    assert minio_storage.get(key) == b"v2"


# ── atomicity ─────────────────────────────────────────────────────────────────


def test_filesystem_write_leaves_no_temp_files(fs_storage, key):
    fs_storage.put(key, b"x")
    leftovers = [p for p in fs_storage.root.rglob("*.tmp")]
    assert leftovers == []


def test_filesystem_failed_write_leaves_no_partial(fs_storage, key, monkeypatch):
    """A crash mid-write must not leave a partial file for list() to find."""
    import os as _os

    def boom(*a, **k):
        raise OSError("disk full")

    fs_storage.put(key, b"good")
    monkeypatch.setattr(_os, "replace", boom)
    with pytest.raises(OSError):
        fs_storage.put(key, b"bad")
    # Original intact, no temp file left behind.
    assert fs_storage.get(key) == b"good"
    assert list(fs_storage.root.rglob("*.tmp")) == []


# ── factory ───────────────────────────────────────────────────────────────────


def test_factory_builds_filesystem(tmp_path):
    assert isinstance(get_storage("filesystem", root=tmp_path), FilesystemStorage)


def test_factory_rejects_unknown_backend():
    with pytest.raises(ValueError, match="unknown STORAGE_BACKEND"):
        get_storage("dropbox")
