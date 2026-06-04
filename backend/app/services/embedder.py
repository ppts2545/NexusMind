from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


@lru_cache(maxsize=1)
def _load_model() -> SentenceTransformer:
    logger.info("loading_embedding_model", model=settings.EMBEDDING_MODEL)
    return SentenceTransformer(settings.EMBEDDING_MODEL)


class Embedder:
    def __init__(self) -> None:
        self._model = _load_model()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        embeddings: np.ndarray = self._model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return embeddings.tolist()

    def embed_query(self, query: str) -> list[float]:
        return self.embed([query])[0]
