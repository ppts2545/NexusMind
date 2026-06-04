import time

import anthropic

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.query import Citation, RAGResponse, SearchResult
from app.services.embedder import Embedder
from app.services.ranker import HybridRanker
from app.services.vector_store import VectorStore

logger = get_logger(__name__)
settings = get_settings()

_SYSTEM_PROMPT = """You are NexusMind, an expert research assistant.
Answer the user's question based solely on the provided context passages.
If the context does not contain enough information, say so clearly.
Always be precise, cite key facts, and avoid hallucination."""


class RAGEngine:
    def __init__(self) -> None:
        self.embedder = Embedder()
        self.vector_store = VectorStore()
        self.ranker = HybridRanker()
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict | None = None,
    ) -> tuple[list[SearchResult], int]:
        t0 = time.monotonic()
        query_vec = self.embedder.embed_query(query)

        raw_matches = await self.vector_store.query(
            query_embedding=query_vec,
            top_k=settings.TOP_K_RETRIEVAL,
            where=filters,
        )

        candidates = [
            {
                "id": m.id,
                "content": m.content,
                "score": m.score,
                "document_id": m.meta.get("document_id", ""),
                "document_title": m.meta.get("document_title", ""),
                "meta": m.meta,
            }
            for m in raw_matches
        ]

        reranked = self.ranker.rerank(query, candidates, top_k=top_k)

        results = [
            SearchResult(
                chunk_id=r.id,
                document_id=r.document_id,
                document_title=r.document_title,
                content=r.content,
                score=r.final_score,
                rank=r.rank,
                meta=r.meta,
            )
            for r in reranked
        ]

        latency_ms = int((time.monotonic() - t0) * 1000)
        return results, latency_ms

    async def answer(
        self,
        query: str,
        top_k: int = 5,
        filters: dict | None = None,
        system_prompt: str | None = None,
    ) -> RAGResponse:
        t0 = time.monotonic()
        results, _ = await self.search(query, top_k=top_k, filters=filters)

        context_blocks = "\n\n".join(
            f"[{i+1}] {r.document_title}\n{r.content}" for i, r in enumerate(results)
        )
        user_message = f"Context:\n{context_blocks}\n\nQuestion: {query}"

        # Build messages with prompt caching for the context (reduces cost on repeated queries)
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": user_message,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            }
        ]

        response = self.client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=settings.MAX_TOKENS,
            system=system_prompt or _SYSTEM_PROMPT,
            messages=messages,
            betas=["prompt-caching-2024-07-31"],
        )

        answer_text = response.content[0].text
        latency_ms = int((time.monotonic() - t0) * 1000)

        citations = [
            Citation(
                document_id=r.document_id,
                document_title=r.document_title,
                chunk_content=r.content[:200],
                score=r.score,
            )
            for r in results
        ]

        logger.info("rag_answer_generated", latency_ms=latency_ms, citations=len(citations))
        return RAGResponse(
            query=query,
            answer=answer_text,
            citations=citations,
            latency_ms=latency_ms,
            model=settings.CLAUDE_MODEL,
        )
