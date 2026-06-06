"""Website source — wraps the existing production-grade WebCrawler."""
from __future__ import annotations

from app.crawler.config import CrawlerConfig
from app.crawler.crawler import WebCrawler
from app.domain.document import Document, SourceType
from app.sources.base import BaseSource


class WebsiteSource(BaseSource):
    """
    Crawl one or more seed URLs and produce ``Document`` objects.

    Uses the existing BFS async crawler with robots.txt compliance,
    sitemap seeding, politeness delays, and content deduplication.
    """

    def __init__(
        self,
        urls: list[str],
        max_depth: int = 2,
        max_pages: int = 50,
        follow_external: bool = False,
        config: CrawlerConfig | None = None,
    ) -> None:
        self._urls = urls
        self._max_depth = max_depth
        self._max_pages = max_pages
        self._follow_external = follow_external
        self._config = config or CrawlerConfig()

    async def load(self) -> list[Document]:
        crawler = WebCrawler(self._config)
        documents: list[Document] = []

        for url in self._urls:
            pages = await crawler.crawl(
                url,
                max_depth=self._max_depth,
                max_pages=self._max_pages,
                follow_external=self._follow_external,
            )
            for page in pages:
                documents.append(
                    Document(
                        source=page.url,
                        source_type=SourceType.WEB,
                        url=page.url,
                        title=page.title,
                        text=page.content,
                        language=page.language or "en",
                        metadata={
                            "depth": page.depth,
                            "content_hash": page.content_hash,
                            "crawled_at": page.crawled_at.isoformat(),
                            "meta": page.meta.to_dict() if page.meta else {},
                        },
                    )
                )

        return documents
