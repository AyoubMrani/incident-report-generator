"""
shared/storage/minio.py — S3-compatible object storage.

Uses boto3 against MinIO's S3 API, so the same code runs unchanged against AWS
S3 if this ever leaves the local stack: only the endpoint URL and credentials
change.

Notes on the choices that are not obvious:

* **`s3v4` signatures and `path` addressing.** MinIO is reached by hostname
  (`http://minio:9000`), and virtual-host addressing would turn that into
  `http://bucket.minio:9000`, which does not resolve inside compose.

* **Bucket creation is attempted once, at construction.** A `put` that has to
  check-then-create on every call pays two extra round trips forever to handle
  a condition that is true for the first second of the bucket's life.

* **Versioning is enabled by `minio-init` on an empty bucket**, not here.
  Turning it on after objects exist leaves those objects at version `null`,
  which silently breaks point-in-time reads for exactly the data that predates
  the change.
"""

from __future__ import annotations

import os
from typing import Any

from app.shared.storage.base import (
    ObjectNotFoundError,
    Storage,
    StorageError,
    StoredObject,
    validate_key,
)


class MinioStorage(Storage):
    def __init__(
        self,
        *,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        region: str = "us-east-1",
        create_bucket: bool = True,
    ):
        import boto3
        from botocore.client import Config

        self.endpoint = endpoint or os.environ.get(
            "MINIO_ENDPOINT", "http://localhost:9000"
        )
        self.bucket = bucket or os.environ.get("REPORTS_BUCKET", "ntt-reports")
        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=access_key
            or os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
            aws_secret_access_key=secret_key
            or os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
            region_name=region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        if create_bucket:
            self._ensure_bucket()

    # ── internals ─────────────────────────────────────────────────────────────

    def _ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError

        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in ("404", "NoSuchBucket", "NotFound"):
                # 403 usually means the bucket exists but belongs to someone
                # else; creating it would fail anyway and mask the real cause.
                return
            try:
                self._client.create_bucket(Bucket=self.bucket)
            except ClientError:
                # Lost a race with another worker doing the same thing.
                pass

    @staticmethod
    def _is_missing(exc: Any) -> bool:
        code = exc.response.get("Error", {}).get("Code", "")
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return code in ("404", "NoSuchKey", "NotFound") or status == 404

    # ── interface ─────────────────────────────────────────────────────────────

    def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        from botocore.exceptions import BotoCoreError, ClientError

        validate_key(key)
        try:
            resp = self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                # S3 user-metadata must be ASCII header values; a report title
                # with an accent would otherwise fail the whole upload.
                Metadata={
                    k: str(v).encode("ascii", "replace").decode("ascii")
                    for k, v in (metadata or {}).items()
                },
            )
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"put failed for {key}: {exc}") from exc

        return StoredObject(
            key=key,
            size=len(data),
            etag=(resp.get("ETag") or "").strip('"'),
            version_id=resp.get("VersionId"),
            content_type=content_type,
        )

    def get(self, key: str, version_id: str | None = None) -> bytes:
        from botocore.exceptions import BotoCoreError, ClientError

        validate_key(key)
        kwargs: dict[str, Any] = {"Bucket": self.bucket, "Key": key}
        if version_id:
            kwargs["VersionId"] = version_id
        try:
            return self._client.get_object(**kwargs)["Body"].read()
        except ClientError as exc:
            if self._is_missing(exc):
                raise ObjectNotFoundError(key) from exc
            raise StorageError(f"get failed for {key}: {exc}") from exc
        except BotoCoreError as exc:
            raise StorageError(f"get failed for {key}: {exc}") from exc

    def delete(self, key: str) -> bool:
        """Delete `key`.

        On a versioned bucket this writes a delete marker rather than removing
        history, so prior versions remain recoverable — which is the point of
        enabling versioning for incident records.
        """
        from botocore.exceptions import BotoCoreError, ClientError

        validate_key(key)
        existed = self.exists(key)
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"delete failed for {key}: {exc}") from exc
        return existed

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        validate_key(key)
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if self._is_missing(exc):
                return False
            raise StorageError(f"exists failed for {key}: {exc}") from exc

    def list(self, prefix: str = "") -> list[StoredObject]:
        from botocore.exceptions import BotoCoreError, ClientError

        out: list[StoredObject] = []
        try:
            # Paginated: list_objects_v2 caps at 1000 keys per call, and a
            # single-call implementation would silently truncate the catalog
            # once the corpus outgrows that.
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    out.append(
                        StoredObject(
                            key=obj["Key"],
                            size=obj["Size"],
                            etag=(obj.get("ETag") or "").strip('"'),
                            last_modified=obj["LastModified"].timestamp(),
                        )
                    )
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"list failed for {prefix!r}: {exc}") from exc

        out.sort(key=lambda o: o.last_modified, reverse=True)
        return out

    def list_versions(self, key: str) -> list[StoredObject]:
        """Every stored version of one key, newest first.

        This is what the versioned bucket buys: the audit trail for a report
        that was edited after the incident was closed.
        """
        from botocore.exceptions import BotoCoreError, ClientError

        validate_key(key)
        try:
            resp = self._client.list_object_versions(
                Bucket=self.bucket, Prefix=key
            )
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"list_versions failed for {key}: {exc}") from exc

        versions = [
            StoredObject(
                key=v["Key"],
                size=v.get("Size", 0),
                etag=(v.get("ETag") or "").strip('"'),
                version_id=v.get("VersionId"),
                last_modified=v["LastModified"].timestamp(),
            )
            for v in resp.get("Versions", [])
            if v["Key"] == key
        ]
        versions.sort(key=lambda o: o.last_modified, reverse=True)
        return versions

    def presigned_url(self, key: str, expires_in: int = 3600) -> str | None:
        from botocore.exceptions import BotoCoreError, ClientError

        validate_key(key)
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except (ClientError, BotoCoreError):
            return None

    def health(self) -> bool:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            self._client.head_bucket(Bucket=self.bucket)
            return True
        except (ClientError, BotoCoreError):
            return False
