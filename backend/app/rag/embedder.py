"""Sentence-Transformer embedder with batch processing."""
from __future__ import annotations

import asyncio
from functools import lru_cache


@lru_cache(maxsize=1)
def _load_model(model_name: str):
    from sentence_transformers import SentenceTransformer  # type: ignore[import]
    return SentenceTransformer(model_name)


class Embedder:
    def __init__(self, model_name: str | None = None, batch_size: int | None = None) -> None:
        from app.core.config import get_settings
        s = get_settings()
        self._model_name = model_name or s.EMBEDDING_MODEL
        self._batch_size = batch_size or s.EMBEDDING_BATCH_SIZE

    @property
    def dimension(self) -> int:
        from app.core.config import get_settings
        return get_settings().EMBEDDING_DIMENSION

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = _load_model(self._model_name)
        embeddings = model.encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    async def embed_async(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self.embed, texts)

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

    async def embed_one_async(self, text: str) -> list[float]:
        return await asyncio.to_thread(self.embed_one, text)
