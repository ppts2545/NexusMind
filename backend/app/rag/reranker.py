"""Hybrid reranker — combines vector similarity + BM25 via Reciprocal Rank Fusion."""
from __future__ import annotations

import math
from collections import Counter

from app.rag.vector_store.base import VectorSearchResult


def _bm25_score(query_tokens: list[str], doc_tokens: list[str], k1: float = 1.5, b: float = 0.75) -> float:
    avg_len = 200
    doc_len = len(doc_tokens)
    tf = Counter(doc_tokens)
    score = 0.0
    for token in query_tokens:
        if token in tf:
            f = tf[token]
            idf = math.log(2)  # simplified — treat each term as existing in ~50% of docs
            numerator = f * (k1 + 1)
            denominator = f + k1 * (1 - b + b * doc_len / avg_len)
            score += idf * (numerator / denominator)
    return score


class HybridReranker:
    """
    Combines vector similarity score (70%) and BM25 term overlap (30%)
    using Reciprocal Rank Fusion for a final ranked list.
    """

    def __init__(self, vector_weight: float = 0.7, bm25_weight: float = 0.3, rrf_k: int = 60) -> None:
        self._vw = vector_weight
        self._bw = bm25_weight
        self._rrf_k = rrf_k

    def rerank(self, query: str, results: list[VectorSearchResult], top_k: int = 5) -> list[VectorSearchResult]:
        if not results:
            return []

        query_tokens = query.lower().split()

        # Compute BM25 scores
        bm25_scores = {
            r.id: _bm25_score(query_tokens, r.content.lower().split())
            for r in results
        }

        # Sort by vector similarity (already sorted from vector store)
        vector_ranked = sorted(results, key=lambda r: r.score, reverse=True)
        bm25_ranked = sorted(results, key=lambda r: bm25_scores[r.id], reverse=True)

        # Reciprocal Rank Fusion
        rrf_scores: dict[str, float] = {}
        for rank, r in enumerate(vector_ranked):
            rrf_scores[r.id] = rrf_scores.get(r.id, 0) + self._vw / (self._rrf_k + rank + 1)
        for rank, r in enumerate(bm25_ranked):
            rrf_scores[r.id] = rrf_scores.get(r.id, 0) + self._bw / (self._rrf_k + rank + 1)

        # Sort by combined RRF score and assign final scores
        id_to_result = {r.id: r for r in results}
        sorted_ids = sorted(rrf_scores, key=lambda id_: rrf_scores[id_], reverse=True)

        reranked: list[VectorSearchResult] = []
        for id_ in sorted_ids[:top_k]:
            r = id_to_result[id_]
            reranked.append(
                VectorSearchResult(
                    id=r.id,
                    score=rrf_scores[id_],
                    document_id=r.document_id,
                    document_title=r.document_title,
                    content=r.content,
                    metadata=r.metadata,
                )
            )

        return reranked
