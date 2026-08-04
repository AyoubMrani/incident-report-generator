"""
shared/storage/factory.py — backend selection.

Same shape as `shared/llm/provider.get_provider`: one function, env-driven,
with an explicit error for an unknown name rather than a silent default. A
typo in STORAGE_BACKEND that quietly fell back to the filesystem would write
reports somewhere nothing else reads them.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.shared.storage.base import Storage

_FILESYSTEM = {"filesystem", "file", "local", "fs"}
_MINIO = {"minio", "s3"}


def get_storage(
    backend: str | None = None, *, root: str | Path | None = None
) -> Storage:
    """Build the configured storage backend.

    `root` is the filesystem directory, used only by the filesystem backend;
    it is accepted here so callers can pass REPORTS_DIR without branching on
    which backend they are about to get.
    """
    name = (backend or os.environ.get("STORAGE_BACKEND", "filesystem")).strip().lower()

    if name in _FILESYSTEM:
        from app.shared.storage.filesystem import FilesystemStorage

        return FilesystemStorage(root or os.environ.get("REPORTS_DIR", "reports"))

    if name in _MINIO:
        from app.shared.storage.minio import MinioStorage

        return MinioStorage()

    raise ValueError(
        f"unknown STORAGE_BACKEND {name!r}; expected one of: "
        f"{', '.join(sorted(_FILESYSTEM | _MINIO))}"
    )
