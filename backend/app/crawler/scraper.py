"""
Article and feed scrapers for structured content extraction.

``ArticleScraper`` — fetches a single article URL and returns an ``Article``
    with main body text, author, publication date, tags, and images.

``FeedScraper`` — parses RSS 2.0 / Atom feeds via *feedparser* and returns a
    sorted list of ``FeedItem`` objects.
"""
from __future__ import annotations

import time as _time
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

try:
    import feedparser  # type: ignore[import]
    _FEEDPARSER_AVAILABLE = True
except ImportError:
    _FEEDPARSER_AVAILABLE = False

from .adapters import DEFAULT_REGISTRY
from .adapters.base import AdapterRegistry
from .config import CrawlerConfig
from .models import Article, FeedItem
from .utils import (
    clean_text,
    count_words,
    detect_language,
    extract_json_ld,
    get_logger,
    hash_content,
    retry_async,
)

logger = get_logger(__name__)

# CSS selectors tried in priority order to locate the main article body
_CONTENT_SELECTORS: list[str] = [
    "article",
    "main",
    '[role="main"]',
    ".post-content",
    ".article-body",
    ".entry-content",
    ".content-body",
    ".story-content",
    "#content",
    "#main",
]

# Tags stripped from content containers before text extraction
_NOISE_TAGS: list[str] = [
    "script", "style", "nav", "footer", "header",
    "aside", "noscript", "figure", "form",
]


# ---------------------------------------------------------------------------
# ArticleScraper
# ---------------------------------------------------------------------------

class ArticleScraper:
    """
    Fetch and extract structured content from a single article page.

    Uses an ``AdapterRegistry`` to pick a site-specific adapter before falling
    back to the default extraction logic.  Pass a custom registry to support
    additional sites without modifying this class::

        registry = AdapterRegistry([BBCAdapter(), MyCustomAdapter()])
        scraper  = ArticleScraper(registry=registry)
    """

    def __init__(
        self,
        config: Optional[CrawlerConfig] = None,
        registry: Optional[AdapterRegistry] = None,
    ) -> None:
        self._cfg = config or CrawlerConfig.from_env()
        self._registry = registry or DEFAULT_REGISTRY
        self._headers = {
            "User-Agent": self._cfg.user_agent,
            "Accept": "text/html,application/xhtml+xml",
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_content_container(self, soup: BeautifulSoup) -> Optional[Any]:
        """Return the most relevant content element, or ``None``."""
        for selector in _CONTENT_SELECTORS:
            el = soup.select_one(selector)
            if el:
                return el
        return soup.find("body")

    def _clean_container(self, container: Any) -> str:
        """Remove noise tags and return clean text from *container*."""
        for tag in container.find_all(_NOISE_TAGS):
            tag.decompose()
        return clean_text(container.get_text(separator=" "))

    def _extract_images(self, container: Any, base_url: str) -> list[str]:
        """Return deduplicated image ``src`` URLs from *container*."""
        seen: dict[str, None] = {}
        for img in container.find_all("img", src=True):
            src = str(img["src"]).strip()
            if src:
                seen[urljoin(base_url, src)] = None
        return list(seen)

    def _extract_tags(self, soup: BeautifulSoup, json_ld: list[dict[str, Any]]) -> list[str]:
        """
        Aggregate tags from three sources:

        1. ``<meta name="keywords">``
        2. ``<a rel="tag">`` links
        3. JSON-LD ``keywords`` field
        """
        tags: set[str] = set()

        kw_meta = soup.find("meta", attrs={"name": "keywords"})
        if kw_meta and kw_meta.get("content"):
            for k in str(kw_meta["content"]).split(","):
                if k.strip():
                    tags.add(k.strip())

        for a in soup.find_all("a", rel=True):
            if "tag" in (a.get("rel") or []):
                text = a.get_text(strip=True)
                if text:
                    tags.add(text)

        for item in json_ld:
            kw = item.get("keywords", "")
            if isinstance(kw, str):
                for k in kw.split(","):
                    if k.strip():
                        tags.add(k.strip())
            elif isinstance(kw, list):
                tags.update(str(k).strip() for k in kw if str(k).strip())

        return sorted(tags)

    def _extract_author(self, soup: BeautifulSoup, json_ld: list[dict[str, Any]]) -> Optional[str]:
        """
        Return author name from JSON-LD, ``<meta name="author">``, or common
        byline selectors.
        """
        # JSON-LD is most authoritative
        for item in json_ld:
            author = item.get("author")
            if isinstance(author, dict):
                return author.get("name")
            if isinstance(author, list) and author:
                first = author[0]
                return first.get("name") if isinstance(first, dict) else str(first)
            if isinstance(author, str):
                return author

        # <meta name="author">
        meta = soup.find("meta", attrs={"name": "author"})
        if meta and meta.get("content"):
            return str(meta["content"]).strip()

        # Common HTML byline patterns
        for selector in [".author", ".byline", '[rel="author"]', ".post-author", ".entry-author"]:
            el = soup.select_one(selector)
            if el:
                text = clean_text(el.get_text())
                if text:
                    return text

        return None

    def _extract_published_at(
        self,
        soup: BeautifulSoup,
        json_ld: list[dict[str, Any]],
    ) -> Optional[datetime]:
        """
        Parse publication date from JSON-LD, meta tags, or ``<time datetime>``.

        Uses ``python-dateutil`` for flexible ISO-8601 / RFC-2822 parsing.
        """
        date_str: Optional[str] = None

        for item in json_ld:
            date_str = item.get("datePublished") or item.get("dateCreated")
            if date_str:
                break

        if not date_str:
            for attr_name, attr_value in [
                ("property", "article:published_time"),
                ("property", "dateCreated"),
                ("name", "datePublished"),
                ("name", "publish-date"),
                ("name", "date"),
                ("name", "DC.date"),
            ]:
                tag = soup.find("meta", attrs={attr_name: attr_value})
                if tag and tag.get("content"):
                    date_str = str(tag["content"])
                    break

        if not date_str:
            time_tag = soup.find("time", attrs={"datetime": True})
            if time_tag:
                date_str = str(time_tag["datetime"])

        if date_str:
            try:
                from dateutil import parser as dp  # type: ignore[import]
                return dp.parse(date_str)
            except Exception:
                pass

        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @retry_async(
        max_retries=3,
        base_delay=1.0,
        backoff_factor=2.0,
        exceptions=(httpx.HTTPError, httpx.TimeoutException),
    )
    async def scrape(self, url: str) -> Optional[Article]:
        """
        Fetch *url* and return a structured ``Article``, or ``None`` on failure.

        Args:
            url: The article page URL to scrape.

        Returns:
            An ``Article`` dataclass, or ``None`` when the page cannot be
            fetched or contains no useful text content.
        """
        async with httpx.AsyncClient(
            headers=self._headers,
            follow_redirects=True,
            timeout=httpx.Timeout(self._cfg.timeout, connect=self._cfg.connect_timeout),
        ) as client:
            try:
                resp = await client.get(url)
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                logger.warning("article_fetch_error", url=url, error=str(exc))
                raise  # bubble up for retry decorator

        if resp.status_code >= 400:
            logger.warning("article_http_error", url=url, status=resp.status_code)
            return None

        if "text/html" not in resp.headers.get("content-type", ""):
            return None

        final_url = str(resp.url)
        soup = BeautifulSoup(resp.text, "lxml")
        json_ld = extract_json_ld(soup)

        # Pick the adapter for this domain (falls back to BaseSiteAdapter)
        adapter = self._registry.get(final_url)

        title_tag = soup.find("title")
        title = clean_text(title_tag.get_text()) if title_tag else final_url

        # Adapter handles content extraction; fall back to <body> if too sparse
        content = adapter.extract_content(soup) or ""
        if len(content) < self._cfg.min_content_length:
            body = soup.find("body")
            if body:
                content = adapter._clean(body)

        # Images are always extracted from the raw soup (adapter-agnostic)
        container = soup.select_one(adapter.content_selectors[0]) or soup.find("body")
        images = self._extract_images(container, final_url) if container else []

        desc_tag = (
            soup.find("meta", attrs={"name": "description"})
            or soup.find("meta", property="og:description")
        )
        description = str(desc_tag["content"]).strip() if desc_tag and desc_tag.get("content") else None

        logger.info(
            "article_scraped",
            url=final_url,
            adapter=type(adapter).__name__,
            words=count_words(content),
        )

        return Article(
            url=final_url,
            title=title,
            content=content,
            author=adapter.extract_author(soup, json_ld),
            published_at=adapter.extract_published_at(soup, json_ld),
            description=description,
            tags=self._extract_tags(soup, json_ld),
            images=images,
            word_count=count_words(content),
            language=detect_language(content[:2000]),
            content_hash=hash_content(content),
        )


# ---------------------------------------------------------------------------
# FeedScraper
# ---------------------------------------------------------------------------

class FeedScraper:
    """
    Parse RSS 2.0 and Atom feeds into ``FeedItem`` objects.

    Requires the optional ``feedparser`` dependency::

        pip install feedparser

    Items are returned sorted newest-first by publication date.
    """

    def __init__(self, config: Optional[CrawlerConfig] = None) -> None:
        if not _FEEDPARSER_AVAILABLE:
            raise ImportError(
                "feedparser is required for FeedScraper.  "
                "Install it with:  pip install feedparser"
            )
        self._cfg = config or CrawlerConfig.from_env()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_date(self, entry: Any) -> Optional[datetime]:
        """Extract publication date from a feedparser entry struct."""
        for field in ("published_parsed", "updated_parsed", "created_parsed"):
            val = getattr(entry, field, None)
            if val:
                try:
                    return datetime.fromtimestamp(_time.mktime(val))
                except (OverflowError, ValueError, OSError):
                    pass
        return None

    def _parse_author(self, entry: Any) -> Optional[str]:
        """Extract the author name, trying multiple feedparser fields."""
        direct = getattr(entry, "author", None)
        if direct:
            return str(direct)
        detail = entry.get("author_detail") or {}
        return detail.get("name") or None

    def _strip_html(self, text: Optional[str]) -> Optional[str]:
        """Strip HTML markup from a feed summary or content value."""
        if not text:
            return None
        return clean_text(BeautifulSoup(text, "lxml").get_text()) or None

    def _entry_url(self, entry: Any) -> Optional[str]:
        """Return the best URL for a feed entry."""
        return entry.get("link") or entry.get("id") or None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scrape(self, feed_url: str) -> list[FeedItem]:
        """
        Fetch and parse an RSS or Atom feed at *feed_url*.

        Args:
            feed_url: URL of the RSS / Atom feed.

        Returns:
            List of ``FeedItem`` objects sorted newest-first.  Returns an
            empty list when the feed cannot be fetched or parsed.
        """
        async with httpx.AsyncClient(
            headers={"User-Agent": self._cfg.user_agent},
            follow_redirects=True,
            timeout=httpx.Timeout(self._cfg.timeout, connect=self._cfg.connect_timeout),
        ) as client:
            try:
                resp = await client.get(feed_url)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.error("feed_fetch_error", url=feed_url, error=str(exc))
                return []

        parsed = feedparser.parse(resp.text)

        if parsed.bozo and not parsed.entries:
            logger.warning(
                "feed_parse_error",
                url=feed_url,
                reason=str(parsed.get("bozo_exception", "unknown")),
            )
            return []

        items: list[FeedItem] = []
        for entry in parsed.entries:
            url = self._entry_url(entry)
            if not url:
                continue

            raw_summary = (
                entry.get("summary")
                or (entry.get("content") or [{}])[0].get("value")
            )
            tags = [
                t.get("term", "")
                for t in getattr(entry, "tags", [])
                if t.get("term")
            ]

            items.append(
                FeedItem(
                    url=url,
                    title=clean_text(entry.get("title", "")),
                    summary=self._strip_html(raw_summary),
                    author=self._parse_author(entry),
                    published_at=self._parse_date(entry),
                    tags=tags,
                )
            )

        items.sort(key=lambda x: x.published_at or datetime.min, reverse=True)
        logger.info("feed_scraped", url=feed_url, count=len(items))
        return items
