"""
shared/storage/filesystem.py — local-directory backend.

What the app always did, behind the interface. Kept as a first-class backend
rather than a legacy shim: it is what the test suite runs on (no container
needed) and what a single-machine deployment can fall back to.

Writes are atomic — temp file in the same directory, then `os.replace`. The
original code wrote JSON directly and rolled it back by hand if the sibling
markdown write failed; a crash between those two steps left a half-written
file that `list_reports` would skip silently. Atomic replace makes a partial
file unobservable instead.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from app.shared.storage.base import (
    ObjectNotFoundError,
    Storage,
    StoredObject,
    validate_key,
)


class FilesystemStorage(Storage):
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        validate_key(key)
        path = (self.root / key).resolve()
        root = self.root.resolve()
        # Defence in depth: validate_key already rejects traversal, but a
        # symlink inside the root could still point outside it.
        if not str(path).startswith(str(root)):
            raise ObjectNotFoundError(f"key escapes storage root: {key!r}")
        return path

    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Same directory as the target so os.replace stays on one filesystem
        # and is therefore atomic; /tmp could be a different mount.
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

        st = path.stat()
        return StoredObject(
            key=key,
            size=st.st_size,
            last_modified=st.st_mtime,
            content_type=content_type,
        )

    def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(key) from exc

    def delete(self, key: str) -> bool:
        path = self._path(key)
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list(self, prefix: str = "") -> list[StoredObject]:
        base = self.root / prefix if prefix else self.root
        if not base.exists():
            return []
        out: list[StoredObject] = []
        for path in base.rglob("*"):
            if not path.is_file() or path.name.endswith(".tmp"):
                continue
            st = path.stat()
            out.append(
                StoredObject(
                    key=path.relative_to(self.root).as_posix(),
                    size=st.st_size,
                    last_modified=st.st_mtime,
                )
            )
        out.sort(key=lambda o: o.last_modified, reverse=True)
        return out

    def presigned_url(self, key: str, expires_in: int = 3600) -> str | None:
        # No direct URL for local files — the caller streams through the API.
        return None

    def health(self) -> bool:
        return self.root.is_dir() and os.access(self.root, os.W_OK)
