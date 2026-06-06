"""Object storage abstraction — put/get raw HTML, PDFs, clean text."""
from __future__ import annotations

from abc import ABC, abstractmethod


class ObjectStorage(ABC):
    """Pluggable object storage backend (local / S3 / MinIO)."""

    @abstractmethod
    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Store *data* at *key*. Returns the canonical storage URI."""

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """Retrieve raw bytes for *key*. Raises KeyError if absent."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete object at *key*. No-op if absent."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Return True if *key* exists in this storage backend."""

    @abstractmethod
    async def list_prefix(self, prefix: str) -> list[str]:
        """Return all keys that start with *prefix*."""

    # ── Convenience helpers ───────────────────────────────────────────────────

    async def put_text(self, key: str, text: str) -> str:
        return await self.put(key, text.encode("utf-8"), content_type="text/plain; charset=utf-8")

    async def get_text(self, key: str) -> str:
        return (await self.get(key)).decode("utf-8")
