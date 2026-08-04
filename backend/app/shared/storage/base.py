"""
shared/storage/base.py — the storage interface.

Deliberately narrow: put, get, delete, exists, list, and a presigned URL. A
wider interface (rename, copy, append) would be easy to add and hard to
implement faithfully on both a filesystem and an object store, and nothing in
the report flow needs it.

Keys are POSIX-style relative paths (`reports/inc_42/report.json`). Both
backends treat them the same way, so a key written by one is findable by the
other — which is what makes the migration verifiable.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass


class StorageError(Exception):
    """Base for storage failures."""


class ObjectNotFoundError(StorageError):
    """Requested key does not exist."""


class InvalidKeyError(StorageError):
    """Key is empty, absolute, or escapes its prefix."""


@dataclass(frozen=True)
class StoredObject:
    """What a write returned, and what a listing yields."""

    key: str
    size: int
    etag: str = ""
    version_id: str | None = None
    last_modified: float = 0.0
    content_type: str = "application/octet-stream"


# Characters that break a key regardless of backend: control characters (they
# corrupt S3's XML responses and are illegal in filenames) and backslash (a path
# separator on Windows, so it could escape a directory there).
_FORBIDDEN = re.compile(r"[\x00-\x1f\x7f\\]")


def validate_key(key: str) -> str:
    """Reject keys that could escape the bucket or prefix.

    Deliberately permissive about the character set. Real report filenames
    contain spaces and accents — "INC0012001_VPN clients unable to
    establish tunnel.json" is the actual naming convention here — and S3 keys
    allow them. An earlier stricter rule (`[A-Za-z0-9._/-]` only) rejected 80
    of 93 existing reports, which is a data-loss bug wearing a safety costume.

    What is enforced is what actually matters:
      * no absolute paths, so a key cannot address outside the root;
      * no `..` segment, so it cannot climb out — this matters even in object
        storage, because the filesystem backend resolves keys into real
        directories and the two backends must refuse the same things;
      * no control characters or backslashes.
    """
    if not key or not key.strip():
        raise InvalidKeyError("storage key must not be empty")
    if key.startswith("/"):
        raise InvalidKeyError(f"storage key must be relative: {key!r}")
    if _FORBIDDEN.search(key):
        raise InvalidKeyError(f"illegal character in storage key: {key!r}")
    if ".." in key.split("/"):
        raise InvalidKeyError(f"path traversal in storage key: {key!r}")
    return key


class Storage(ABC):
    """Blob storage backend."""

    @abstractmethod
    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        """Write `data` at `key`, overwriting. Returns the stored object."""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Read `key`. Raises ObjectNotFoundError if absent."""

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Remove `key`. True if it existed, False if it did not."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """True if `key` is present."""

    @abstractmethod
    def list(self, prefix: str = "") -> list[StoredObject]:
        """Objects under `prefix`, newest first."""

    @abstractmethod
    def presigned_url(self, key: str, expires_in: int = 3600) -> str | None:
        """Time-limited direct download URL, or None if unsupported.

        Filesystem storage returns None: callers must fall back to streaming
        through the API rather than assume a URL is always available.
        """

    def health(self) -> bool:
        """True if the backend is reachable."""
        try:
            self.list("")
            return True
        except Exception:
            return False
