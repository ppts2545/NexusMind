"""S3-compatible storage backend — works with AWS S3 and MinIO."""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.storage.base import ObjectStorage

if TYPE_CHECKING:
    pass


class S3Storage(ObjectStorage):
    """
    Async S3 storage using aioboto3.

    Works with both AWS S3 (set endpoint_url=None) and MinIO
    (set endpoint_url to the MinIO server URL).
    """

    def __init__(
        self,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        endpoint_url: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region
        self._endpoint_url = endpoint_url or None
        self._session: object | None = None

    def _get_session(self):
        if self._session is None:
            import aioboto3  # lazy import — optional dep
            self._session = aioboto3.Session(
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                region_name=self._region,
            )
        return self._session

    def _client_kwargs(self) -> dict:
        kw: dict = {}
        if self._endpoint_url:
            kw["endpoint_url"] = self._endpoint_url
        return kw

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        session = self._get_session()
        async with session.client("s3", **self._client_kwargs()) as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        return f"s3://{self._bucket}/{key}"

    async def get(self, key: str) -> bytes:
        session = self._get_session()
        async with session.client("s3", **self._client_kwargs()) as s3:
            try:
                resp = await s3.get_object(Bucket=self._bucket, Key=key)
                return await resp["Body"].read()
            except Exception as e:
                if "NoSuchKey" in str(type(e).__name__):
                    raise KeyError(f"Object not found: s3://{self._bucket}/{key}") from e
                raise

    async def delete(self, key: str) -> None:
        session = self._get_session()
        async with session.client("s3", **self._client_kwargs()) as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)

    async def exists(self, key: str) -> bool:
        session = self._get_session()
        async with session.client("s3", **self._client_kwargs()) as s3:
            try:
                await s3.head_object(Bucket=self._bucket, Key=key)
                return True
            except Exception:
                return False

    async def list_prefix(self, prefix: str) -> list[str]:
        session = self._get_session()
        keys: list[str] = []
        async with session.client("s3", **self._client_kwargs()) as s3:
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"])
        return keys


def make_storage_from_settings() -> ObjectStorage:
    """Factory — reads app settings and returns the right storage backend."""
    from app.core.config import get_settings
    from app.storage.local import LocalStorage

    settings = get_settings()

    if settings.OBJECT_STORAGE == "local":
        return LocalStorage(settings.LOCAL_STORAGE_ROOT)

    # s3 or minio — use separate bucket instances; caller chooses which
    return S3Storage(
        bucket=settings.S3_BUCKET_RAW,
        access_key=settings.S3_ACCESS_KEY,
        secret_key=settings.S3_SECRET_KEY,
        region=settings.S3_REGION,
        endpoint_url=settings.S3_ENDPOINT_URL if settings.OBJECT_STORAGE == "minio" else None,
    )
