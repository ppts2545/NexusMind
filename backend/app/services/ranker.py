import math
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RankedResult:
    id: str
    document_id: str
    document_title: str
    content: str
    vector_score: float
    bm25_score: float
    final_score: float
    rank: int
    meta: dict


class HybridRanker:
    """
    Combines dense vector similarity with BM25-style term overlap
    using Reciprocal Rank Fusion (RRF).
    """

    def __init__(self, rrf_k: int = 60, vector_weight: float = 0.7, bm25_weight: float = 0.3) -> None:
        self.rrf_k = rrf_k
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight

    def _bm25_score(self, query_terms: set[str], doc_text: str, avg_dl: float = 100.0) -> float:
        k1, b = 1.5, 0.75
        terms = doc_text.lower().split()
        dl = len(terms)
        freq: dict[str, int] = {}
        for t in terms:
            freq[t] = freq.get(t, 0) + 1

        score = 0.0
        for term in query_terms:
            tf = freq.get(term, 0)
            if tf == 0:
                continue
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * dl / max(avg_dl, 1))
            score += numerator / denominator
        return score

    def _rrf(self, rank: int) -> float:
        return 1.0 / (self.rrf_k + rank)

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        top_k: int = 5,
    ) -> list[RankedResult]:
        query_terms = set(query.lower().split())

        scored: list[tuple[dict, float, float]] = []
        for c in candidates:
            bm25 = self._bm25_score(query_terms, c["content"])
            scored.append((c, c["score"], bm25))

        # Sort by vector score for RRF rank
        by_vector = sorted(scored, key=lambda x: x[1], reverse=True)
        by_bm25 = sorted(scored, key=lambda x: x[2], reverse=True)

        vector_ranks = {c[0]["id"]: r + 1 for r, c in enumerate(by_vector)}
        bm25_ranks = {c[0]["id"]: r + 1 for r, c in enumerate(by_bm25)}

        results: list[RankedResult] = []
        for c, vscore, bscore in scored:
            rrf = (
                self.vector_weight * self._rrf(vector_ranks[c["id"]])
                + self.bm25_weight * self._rrf(bm25_ranks[c["id"]])
            )
            results.append(
                RankedResult(
                    id=c["id"],
                    document_id=c.get("document_id", ""),
                    document_title=c.get("document_title", ""),
                    content=c["content"],
                    vector_score=vscore,
                    bm25_score=bscore,
                    final_score=rrf,
                    rank=0,
                    meta=c.get("meta", {}),
                )
            )

        results.sort(key=lambda r: r.final_score, reverse=True)
        for i, r in enumerate(results[:top_k]):
            r.rank = i + 1

        logger.info("reranked", candidates=len(candidates), returned=min(top_k, len(results)))
        return results[:top_k]
