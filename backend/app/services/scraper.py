"""
scraper.py — Structured content extraction utilities.

Provides two scrapers:
- ArticleScraper : fetch a single URL and extract structured article fields
                   (title, author, published date, body text, images, tags)
- FeedScraper    : parse RSS / Atom feeds and return a list of FeedItem entries
"""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Article:
    url: str
    title: str
    content: str
    author: str = ""
    published_at: Optional[datetime] = None
    description: str = ""
    tags: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    word_count: int = 0


@dataclass
class FeedItem:
    url: str
    title: str
    summary: str
    author: str = ""
    published_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Article scraper
# ---------------------------------------------------------------------------

class ArticleScraper:
    """Extract structured article data from a single page URL.

    Tries a series of semantic selectors (article, main, [role=main], common
    CMS class names) to find the main content block before falling back to
    the full <body>.  Strips navigation / sidebar noise first.
    """

    # Ordered list — first match wins
    _CONTENT_SELECTORS = [
        "article",
        "[role='main']",
        "main",
        ".post-content",
        ".article-body",
        ".entry-content",
        ".content-body",
        "#content",
        "#main",
    ]

    def __init__(self) -> None:
        self._headers = {"User-Agent": settings.CRAWLER_USER_AGENT}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_main_content(self, soup: BeautifulSoup) -> BeautifulSoup:
        for selector in self._CONTENT_SELECTORS:
            el = soup.select_one(selector)
            if el:
                return el
        return soup.find("body") or soup

    def _clean_text(self, element) -> str:
        for tag in element(["script", "style", "nav", "footer", "header", "aside", "figure"]):
            tag.decompose()
        return " ".join(element.get_text(separator=" ").split())

    def _extract_images(self, element, base_url: str) -> list[str]:
        seen: set[str] = set()
        images: list[str] = []
        for img in element.find_all("img", src=True):
            full = urljoin(base_url, img["src"])
            if full.startswith("http") and full not in seen:
                seen.add(full)
                images.append(full)
                if len(images) >= 10:  # cap to avoid bloat
                    break
        return images

    def _meta_content(self, soup: BeautifulSoup, name_pattern: str, by: str = "name") -> str:
        tag = soup.find("meta", attrs={by: re.compile(name_pattern, re.I)})
        return tag.get("content", "") if tag else ""

    def _parse_published_at(self, soup: BeautifulSoup) -> Optional[datetime]:
        for attr_name in ("article:published_time", "datePublished", "date"):
            date_tag = soup.find("meta", property=attr_name) or soup.find(
                "meta", attrs={"name": attr_name}
            )
            if date_tag:
                raw = date_tag.get("content", "").rstrip("Z")
                try:
                    return datetime.fromisoformat(raw)
                except ValueError:
                    continue
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scrape(self, url: str) -> Article | None:
        """Fetch *url* and return a structured Article, or None on failure."""
        async with httpx.AsyncClient(headers=self._headers) as client:
            try:
                resp = await client.get(url, timeout=settings.CRAWLER_TIMEOUT, follow_redirects=True)
                if "text/html" not in resp.headers.get("content-type", ""):
                    return None

                soup = BeautifulSoup(resp.text, "html.parser")
                resolved_url = str(resp.url)

                title = soup.title.string.strip() if soup.title else resolved_url
                description = self._meta_content(soup, "description")
                author = self._meta_content(soup, "author")

                kw_raw = self._meta_content(soup, "keywords")
                tags = [k.strip() for k in kw_raw.split(",") if k.strip()]

                published_at = self._parse_published_at(soup)

                main = self._find_main_content(soup)
                content = self._clean_text(main)
                images = self._extract_images(main, resolved_url)
                word_count = len(content.split())

                return Article(
                    url=resolved_url,
                    title=title,
                    content=content,
                    author=author,
                    published_at=published_at,
                    description=description,
                    tags=tags,
                    images=images,
                    word_count=word_count,
                )
            except Exception as exc:
                logger.warning("article_scrape_error", url=url, error=str(exc))
                return None

    async def scrape_many(self, urls: list[str], concurrency: int = 5) -> list[Article]:
        """Scrape multiple URLs concurrently (bounded by *concurrency*)."""
        sem = asyncio.Semaphore(concurrency)

        async def _bounded(url: str) -> Article | None:
            async with sem:
                return await self.scrape(url)

        results = await asyncio.gather(*[_bounded(u) for u in urls], return_exceptions=False)
        articles = [r for r in results if isinstance(r, Article)]
        logger.info("scrape_many_done", total=len(urls), success=len(articles))
        return articles


# ---------------------------------------------------------------------------
# Feed scraper (RSS / Atom)
# ---------------------------------------------------------------------------

class FeedScraper:
    """Parse an RSS or Atom feed URL and return a list of FeedItem entries.

    Requires the optional ``feedparser`` package:
        pip install feedparser
    """

    def __init__(self) -> None:
        self._headers = {
            "User-Agent": settings.CRAWLER_USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
        }

    async def fetch(self, feed_url: str) -> list[FeedItem]:
        """Download and parse *feed_url*.  Returns an empty list on any error."""
        try:
            import feedparser
        except ImportError:
            logger.error("feedparser_not_installed", hint="pip install feedparser")
            return []

        async with httpx.AsyncClient(headers=self._headers) as client:
            try:
                resp = await client.get(feed_url, timeout=15, follow_redirects=True)
            except Exception as exc:
                logger.warning("feed_fetch_error", url=feed_url, error=str(exc))
                return []

        feed = feedparser.parse(resp.text)
        items: list[FeedItem] = []

        for entry in feed.entries:
            published_at: Optional[datetime] = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                from time import mktime
                published_at = datetime.fromtimestamp(mktime(entry.published_parsed))

            summary = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()

            items.append(FeedItem(
                url=entry.get("link", ""),
                title=entry.get("title", ""),
                summary=summary,
                author=entry.get("author", ""),
                published_at=published_at,
            ))

        logger.info("feed_fetched", url=feed_url, items=len(items))
        return items

    async def fetch_many(self, feed_urls: list[str]) -> list[FeedItem]:
        """Fetch multiple feeds concurrently and merge results."""
        results = await asyncio.gather(*[self.fetch(u) for u in feed_urls])
        all_items = [item for feed_items in results for item in feed_items]
        logger.info("feeds_fetched_total", feeds=len(feed_urls), items=len(all_items))
        return all_items
