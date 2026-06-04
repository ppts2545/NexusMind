import asyncio
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class CrawledPage:
    url: str
    title: str
    content: str
    links: list[str] = field(default_factory=list)
    status_code: int = 200


class WebCrawler:
    def __init__(self) -> None:
        self._headers = {"User-Agent": settings.CRAWLER_USER_AGENT}

    def _is_same_domain(self, base: str, url: str) -> bool:
        return urlparse(base).netloc == urlparse(url).netloc

    def _extract_text(self, soup: BeautifulSoup) -> str:
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        return " ".join(soup.get_text(separator=" ").split())

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        links: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full = urljoin(base_url, href)
            parsed = urlparse(full)
            if parsed.scheme in ("http", "https") and parsed.fragment == "":
                links.append(full.rstrip("/"))
        return list(dict.fromkeys(links))  # deduplicate while preserving order

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> CrawledPage | None:
        try:
            resp = await client.get(url, timeout=settings.CRAWLER_TIMEOUT, follow_redirects=True)
            if "text/html" not in resp.headers.get("content-type", ""):
                return None
            soup = BeautifulSoup(resp.text, "html.parser")
            title = soup.title.string.strip() if soup.title else url
            return CrawledPage(
                url=str(resp.url),
                title=title,
                content=self._extract_text(soup),
                links=self._extract_links(soup, str(resp.url)),
                status_code=resp.status_code,
            )
        except Exception as exc:
            logger.warning("crawl_fetch_error", url=url, error=str(exc))
            return None

    async def crawl(
        self,
        start_url: str,
        max_depth: int | None = None,
        max_pages: int | None = None,
        follow_external: bool = False,
    ) -> list[CrawledPage]:
        max_depth = max_depth or settings.CRAWLER_MAX_DEPTH
        max_pages = max_pages or settings.CRAWLER_MAX_PAGES

        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(start_url.rstrip("/"), 0)]
        pages: list[CrawledPage] = []

        async with httpx.AsyncClient(headers=self._headers) as client:
            while queue and len(pages) < max_pages:
                url, depth = queue.pop(0)
                if url in visited or depth > max_depth:
                    continue
                visited.add(url)

                page = await self._fetch(client, url)
                if page is None:
                    continue

                pages.append(page)
                logger.info("crawled", url=page.url, depth=depth, total=len(pages))

                if depth < max_depth:
                    for link in page.links:
                        if link not in visited:
                            if follow_external or self._is_same_domain(start_url, link):
                                queue.append((link, depth + 1))

        logger.info("crawl_complete", pages=len(pages), start_url=start_url)
        return pages
