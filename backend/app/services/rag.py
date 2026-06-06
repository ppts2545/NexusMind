"""RAG service — query → retrieve → rerank → optional fallback → LLM."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.logging import get_logger
from app.rag.embedder import Embedder
from app.rag.prompt_builder import PromptBuilder
from app.rag.retriever import Retriever
from app.rag.vector_store.base import VectorSearchResult, VectorStore
from app.search.fallback import WebSearchFallback
from app.storage.base import ObjectStorage

logger = get_logger(__name__)


@dataclass
class SearchResponse:
    query: str
    results: list[VectorSearchResult]
    latency_ms: int
    confidence: float


@dataclass
class RAGResponse:
    query: str
    answer: str
    citations: list[dict]
    latency_ms: int
    model: str
    used_web_fallback: bool = False
    confidence: float = 0.0


class RAGService:
    """
    End-to-end RAG: query → embed → retrieve → rerank → (fallback?) → LLM.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        storage: ObjectStorage,
        embedder: Embedder | None = None,
    ) -> None:
        self._vector_store = vector_store
        self._storage = storage
        self._settings = get_settings()
        self._embedder = embedder or Embedder()
        self._retriever = Retriever(vector_store, self._embedder)
        self._prompt_builder = PromptBuilder()
        self._fallback = WebSearchFallback()

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict | None = None,
    ) -> SearchResponse:
        t0 = time.monotonic()
        top_k = top_k or self._settings.TOP_K_RERANK

        results, confidence = await self._retriever.retrieve(
            query,
            top_k_retrieve=self._settings.TOP_K_RETRIEVAL,
            top_k_rerank=top_k,
            filters=filters,
        )

        return SearchResponse(
            query=query,
            results=results,
            latency_ms=int((time.monotonic() - t0) * 1000),
            confidence=confidence,
        )

    async def answer(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict | None = None,
        system_prompt: str | None = None,
    ) -> RAGResponse:
        t0 = time.monotonic()
        top_k = top_k or self._settings.TOP_K_RERANK

        results, confidence = await self._retriever.retrieve(
            query,
            top_k_retrieve=self._settings.TOP_K_RETRIEVAL,
            top_k_rerank=top_k,
            filters=filters,
        )

        used_fallback = False

        if confidence < self._settings.RAG_CONFIDENCE_THRESHOLD:
            logger.info("low_confidence_fallback", confidence=confidence, query=query)
            web_results = await self._fallback.search_and_backfill(
                query, self._vector_store, self._embedder, self._storage
            )
            if web_results:
                used_fallback = True
                # Convert web results to VectorSearchResult for unified prompt building
                from app.rag.vector_store.base import VectorSearchResult
                results = [
                    VectorSearchResult(
                        id=f"web_{i}",
                        score=r.score,
                        document_id=f"web_{i}",
                        document_title=r.title,
                        content=r.content,
                        metadata={"url": r.url, "web_fallback": True},
                    )
                    for i, r in enumerate(web_results)
                ]

        if not results:
            return RAGResponse(
                query=query,
                answer="I could not find relevant information to answer your question.",
                citations=[],
                latency_ms=int((time.monotonic() - t0) * 1000),
                model=self._settings.CLAUDE_MODEL,
                used_web_fallback=used_fallback,
                confidence=confidence,
            )

        system_prompt_built, user_message = self._prompt_builder.build(
            query, results, system_override=system_prompt
        )
        citations = self._prompt_builder.format_citations(results)

        answer = await self._call_llm(system_prompt_built, user_message)

        return RAGResponse(
            query=query,
            answer=answer,
            citations=citations,
            latency_ms=int((time.monotonic() - t0) * 1000),
            model=self._settings.CLAUDE_MODEL,
            used_web_fallback=used_fallback,
            confidence=confidence,
        )

    async def _call_llm(self, system: str, user: str) -> str:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self._settings.ANTHROPIC_API_KEY)

        # Use prompt caching on the system prompt (context is expensive to re-encode)
        message = await client.messages.create(
            model=self._settings.CLAUDE_MODEL,
            max_tokens=self._settings.MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user}],
        )

        return message.content[0].text
