"""
shared/storage — pluggable blob storage for report artifacts.

Mirrors the `shared/llm/` provider pattern: one interface, two implementations,
chosen by env var. The filesystem backend is what the app has always used and
stays the default for tests (no container needed); MinIO is what the platform
runs on.

    STORAGE_BACKEND=minio       # object storage, versioned
    STORAGE_BACKEND=filesystem  # local directory (default when unset)
"""

from app.shared.storage.base import (
    ObjectNotFoundError,
    StorageError,
    StoredObject,
)
from app.shared.storage.factory import get_storage

__all__ = [
    "ObjectNotFoundError",
    "StorageError",
    "StoredObject",
    "get_storage",
]
