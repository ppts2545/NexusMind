"""Local filesystem storage — for development and testing."""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.storage.base import ObjectStorage


class LocalStorage(ObjectStorage):
    """Stores objects as files under *root_dir*."""

    def __init__(self, root_dir: str) -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self._root / key).resolve()
        # Prevent path traversal
        if not str(p).startswith(str(self._root)):
            raise ValueError(f"Invalid key: {key}")
        return p

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        return f"local://{key}"

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise KeyError(f"Object not found: {key}")
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            await asyncio.to_thread(path.unlink)

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()

    async def list_prefix(self, prefix: str) -> list[str]:
        base = self._path(prefix) if prefix.endswith("/") else self._path(prefix).parent
        if not base.exists():
            return []
        results: list[str] = []
        for p in base.rglob("*"):
            if p.is_file():
                rel = p.relative_to(self._root)
                key = str(rel)
                if key.startswith(prefix):
                    results.append(key)
        return results
