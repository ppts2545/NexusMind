"""Web search fallback — triggered when RAG retrieval confidence is too low."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class WebSearchResult:
    url: str
    title: str
    content: str
    score: float = 1.0


class WebSearchFallback:
    """
    Falls back to Tavily web search when RAG confidence is below threshold.

    Flow:
        1. Search Tavily for relevant pages
        2. Optionally scrape full content via ArticleScraper
        3. Return context chunks for LLM
        4. Optionally back-fill into Master Storage + Vector DB

    Usage::

        fallback = WebSearchFallback()
        results = await fallback.search("What is RAG?")
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    async def search(self, query: str) -> list[WebSearchResult]:
        """Call Tavily and return structured results."""
        if not self._settings.TAVILY_API_KEY:
            logger.warning("tavily_key_missing", query=query)
            return []

        try:
            from tavily import AsyncTavilyClient  # type: ignore[import]
        except ImportError:
            logger.error("tavily_not_installed")
            return []

        client = AsyncTavilyClient(api_key=self._settings.TAVILY_API_KEY)

        try:
            response = await client.search(
                query=query,
                max_results=self._settings.WEB_SEARCH_MAX_RESULTS,
                search_depth="advanced",
                include_raw_content=True,
            )
        except Exception as exc:
            logger.error("tavily_search_failed", error=str(exc), query=query)
            return []

        results: list[WebSearchResult] = []
        for r in response.get("results", []):
            content = r.get("raw_content") or r.get("content", "")
            if not content.strip():
                continue
            results.append(
                WebSearchResult(
                    url=r.get("url", ""),
                    title=r.get("title", ""),
                    content=content[:4000],
                    score=r.get("score", 1.0),
                )
            )

        logger.info("web_search_done", query=query, results=len(results))
        return results

    async def search_and_backfill(
        self,
        query: str,
        vector_store,
        embedder,
        storage,
    ) -> list[WebSearchResult]:
        """
        Search, then optionally store new content in Master Storage + Vector DB
        so future queries benefit from it.
        """
        results = await self.search(query)
        if not results or not self._settings.WEB_SEARCH_BACKFILL:
            return results

        try:
            await self._backfill(results, vector_store, embedder, storage)
        except Exception as exc:
            logger.warning("backfill_failed", error=str(exc))

        return results

    async def _backfill(self, results: list[WebSearchResult], vector_store, embedder, storage) -> None:
        import uuid
        from app.domain.document import Document, SourceType
        from app.cleaning.cleaner import TextCleaner
        from app.rag.chunker import RecursiveChunker

        cleaner = TextCleaner()
        chunker = RecursiveChunker()

        for result in results:
            doc = Document(
                source=result.url,
                source_type=SourceType.WEB,
                url=result.url,
                title=result.title,
                text=result.content,
            )
            clean = cleaner.clean(doc)
            chunks = chunker.chunk(clean)
            if not chunks:
                continue

            texts = [c.content for c in chunks]
            embeddings = await embedder.embed_async(texts)

            ids = [str(uuid.uuid4()) for _ in chunks]
            metadatas = [
                {
                    "document_id": str(doc.id),
                    "document_title": result.title,
                    "source_url": result.url,
                    "web_fallback": True,
                    **c.metadata,
                }
                for c in chunks
            ]

            await vector_store.upsert(
                ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas
            )

            await storage.put_text(
                f"web_fallback/{doc.id}/clean.txt",
                clean.text,
            )
