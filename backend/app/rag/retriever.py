"""Retriever — orchestrates embed → vector search → rerank."""
from __future__ import annotations

from app.rag.embedder import Embedder
from app.rag.reranker import HybridReranker
from app.rag.vector_store.base import VectorSearchResult, VectorStore


class Retriever:
    def __init__(
        self,
        vector_store: VectorStore,
        embedder: Embedder | None = None,
        reranker: HybridReranker | None = None,
    ) -> None:
        self._store = vector_store
        self._embedder = embedder or Embedder()
        self._reranker = reranker or HybridReranker()

    async def retrieve(
        self,
        query: str,
        top_k_retrieve: int = 10,
        top_k_rerank: int = 5,
        filters: dict | None = None,
        use_hybrid: bool = True,
    ) -> tuple[list[VectorSearchResult], float]:
        """
        Returns (reranked_results, best_score).

        best_score is used to decide whether to trigger web search fallback.
        """
        embedding = await self._embedder.embed_one_async(query)

        if use_hybrid:
            raw_results = await self._store.hybrid_query(
                embedding=embedding, text=query, top_k=top_k_retrieve, filters=filters
            )
        else:
            raw_results = await self._store.query(
                embedding=embedding, top_k=top_k_retrieve, filters=filters
            )

        if not raw_results:
            return [], 0.0

        reranked = self._reranker.rerank(query, raw_results, top_k=top_k_rerank)
        best_score = reranked[0].score if reranked else 0.0
        return reranked, best_score
