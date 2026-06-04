"""
Async BFS web crawler with robots.txt compliance and sitemap seeding.

Key classes
-----------
``RobotsCache``   — fetches /robots.txt once per domain and caches the result.
``SitemapParser`` — recursively parses /sitemap.xml to discover seed URLs.
``WebCrawler``    — orchestrates BFS crawl with concurrency, politeness, and
                    duplicate-content filtering via SHA-256 hashing.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from .config import CrawlerConfig
from .models import CrawledPage, PageMeta
from .utils import (
    clean_text,
    detect_language,
    extract_canonical_url,
    extract_json_ld,
    get_logger,
    hash_content,
    is_same_domain,
    is_valid_url,
    normalize_url,
    retry_async,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# RobotsCache
# ---------------------------------------------------------------------------

class RobotsCache:
    """
    Per-domain robots.txt cache.

    Fetches ``/robots.txt`` at most once per domain per crawler run and stores
    a parsed ``RobotFileParser`` for ``can_fetch()`` queries.  An asyncio lock
    prevents duplicate fetches when multiple coroutines hit the same domain
    concurrently.
    """

    def __init__(self, user_agent: str) -> None:
        self._user_agent = user_agent
        self._cache: dict[str, Optional[RobotFileParser]] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, client: httpx.AsyncClient, url: str) -> bool:
        """
        Return ``True`` if the configured user-agent may crawl *url*.

        Defaults to ``True`` when robots.txt is unreachable or unparseable
        (fail-open policy keeps crawl progress intact).
        """
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        async with self._lock:
            if origin not in self._cache:
                await self._fetch(client, origin)

        rp = self._cache.get(origin)
        if rp is None:
            return True
        return rp.can_fetch(self._user_agent, url)

    async def _fetch(self, client: httpx.AsyncClient, origin: str) -> None:
        """Fetch and parse robots.txt for *origin*, storing result in cache."""
        robots_url = f"{origin}/robots.txt"
        rp = RobotFileParser(robots_url)
        try:
            resp = await client.get(robots_url, timeout=10.0)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
                logger.info("robots_loaded", origin=origin)
            else:
                logger.debug("robots_absent", origin=origin, status=resp.status_code)
        except Exception as exc:
            logger.warning("robots_fetch_error", origin=origin, error=str(exc))
            # Store None so we don't retry this origin on every request
        self._cache[origin] = rp


# ---------------------------------------------------------------------------
# SitemapParser
# ---------------------------------------------------------------------------

class SitemapParser:
    """
    Recursive sitemap parser.

    Handles both *sitemap index* documents (``<sitemapindex>``) and regular
    *URL set* documents (``<urlset>``).  Recursion is capped at depth 3 to
    guard against malformed or circular sitemaps.
    """

    _MAX_RECURSION = 3

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def discover(self, base_url: str) -> list[str]:
        """
        Return all URLs found in the site's sitemap hierarchy.

        Starts from ``<origin>/sitemap.xml``.
        """
        parsed = urlparse(base_url)
        sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
        urls = await self._parse(sitemap_url, depth=0)
        logger.info("sitemap_discovery_done", start=sitemap_url, found=len(urls))
        return urls

    async def _parse(self, url: str, depth: int) -> list[str]:
        """Recursively parse a sitemap URL, returning a flat list of page URLs."""
        if depth > self._MAX_RECURSION:
            return []
        try:
            resp = await self._client.get(url, timeout=15.0)
            if resp.status_code != 200:
                logger.debug("sitemap_not_found", url=url, status=resp.status_code)
                return []
        except Exception as exc:
            logger.warning("sitemap_fetch_error", url=url, error=str(exc))
            return []

        # Use the xml parser so tag names are case-sensitive and correct
        soup = BeautifulSoup(resp.text, "xml")

        # ---- Sitemap index: recurse into each child sitemap ----
        child_sitemaps = soup.find_all("sitemap")
        if child_sitemaps:
            results: list[str] = []
            child_tasks = [
                self._parse(sm.find("loc").text.strip(), depth + 1)
                for sm in child_sitemaps
                if sm.find("loc") and sm.find("loc").text.strip()
            ]
            gathered = await asyncio.gather(*child_tasks, return_exceptions=True)
            for item in gathered:
                if isinstance(item, list):
                    results.extend(item)
            return results

        # ---- URL set: return all <loc> values ----
        locs = soup.find_all("loc")
        return [loc.text.strip() for loc in locs if loc.text.strip()]


# ---------------------------------------------------------------------------
# WebCrawler
# ---------------------------------------------------------------------------

class WebCrawler:
    """
    Production-grade async BFS web crawler.

    Usage::

        config = CrawlerConfig(max_depth=2, max_pages=50)
        crawler = WebCrawler(config)
        pages = await crawler.crawl("https://example.com")

    The crawl honours:
    - ``robots.txt`` (optional, on by default).
    - Per-domain politeness delay.
    - Concurrency cap via ``asyncio.Semaphore``.
    - Content-hash deduplication (skips pages with identical body text).
    - Optional sitemap seeding for broader initial coverage.
    """

    def __init__(self, config: Optional[CrawlerConfig] = None) -> None:
        self._cfg = config or CrawlerConfig.from_env()
        self._request_headers = {
            "User-Agent": self._cfg.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
        }
        # Per-domain last-request wall-clock time and per-domain lock
        self._domain_last_fetch: dict[str, float] = {}
        self._domain_locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _domain_lock(self, domain: str) -> asyncio.Lock:
        """Lazily create and return a per-domain asyncio lock."""
        if domain not in self._domain_locks:
            self._domain_locks[domain] = asyncio.Lock()
        return self._domain_locks[domain]

    async def _polite_delay(self, url: str) -> None:
        """
        Block until the minimum politeness interval has elapsed for the
        domain of *url*, then update the last-fetch timestamp.
        """
        domain = urlparse(url).netloc
        async with self._domain_lock(domain):
            elapsed = time.monotonic() - self._domain_last_fetch.get(domain, 0.0)
            remaining = self._cfg.politeness_delay - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._domain_last_fetch[domain] = time.monotonic()

    # ------------------------------------------------------------------
    # Page-level parsing helpers
    # ------------------------------------------------------------------

    def _parse_meta(self, soup: BeautifulSoup) -> PageMeta:
        """Extract all metadata from the page's ``<head>``."""

        def _meta_content(name: str = "", prop: str = "") -> Optional[str]:
            if name:
                tag = soup.find("meta", attrs={"name": name})
            else:
                tag = soup.find("meta", property=prop)
            if tag and tag.get("content"):
                return str(tag["content"]).strip() or None
            return None

        published_at: Optional[datetime] = None
        pub_str = _meta_content(prop="article:published_time") or _meta_content(name="datePublished")
        if pub_str:
            try:
                from dateutil import parser as dp  # type: ignore[import]
                published_at = dp.parse(pub_str)
            except Exception:
                pass

        raw_kw = _meta_content(name="keywords") or ""
        keywords = [k.strip() for k in raw_kw.split(",") if k.strip()]

        return PageMeta(
            description=_meta_content(name="description"),
            author=_meta_content(name="author"),
            published_at=published_at,
            og_title=_meta_content(prop="og:title"),
            og_image=_meta_content(prop="og:image"),
            keywords=keywords,
        )

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """Return deduplicated, normalised HTTP/HTTPS links found on the page."""
        seen: dict[str, None] = {}
        for a in soup.find_all("a", href=True):
            raw = str(a["href"]).strip()
            if not raw or raw.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            full = normalize_url(urljoin(base_url, raw))
            if is_valid_url(full):
                seen[full] = None
        return list(seen)

    def _extract_text(self, soup: BeautifulSoup) -> str:
        """Remove boilerplate elements and return cleaned body text."""
        for tag in soup.find_all(
            ["script", "style", "nav", "footer", "header", "aside", "noscript"]
        ):
            tag.decompose()
        return clean_text(soup.get_text(separator=" "))

    # ------------------------------------------------------------------
    # Core fetch
    # ------------------------------------------------------------------

    @retry_async(
        max_retries=3,
        base_delay=1.0,
        backoff_factor=2.0,
        exceptions=(httpx.HTTPError, httpx.TimeoutException),
    )
    async def _fetch(
        self,
        client: httpx.AsyncClient,
        url: str,
        depth: int,
        robots: RobotsCache,
    ) -> Optional[CrawledPage]:
        """
        Fetch *url* and return a ``CrawledPage``, or ``None`` on skip/error.

        Network errors are re-raised so the retry decorator can act on them.
        Non-retriable conditions (wrong content-type, 4xx, robots block) return
        ``None`` immediately.
        """
        if self._cfg.respect_robots_txt and not await robots.is_allowed(client, url):
            logger.info("robots_blocked", url=url)
            return None

        await self._polite_delay(url)

        try:
            resp = await client.get(
                url,
                timeout=httpx.Timeout(self._cfg.timeout, connect=self._cfg.connect_timeout),
                follow_redirects=True,
            )
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            # Re-raise so the retry decorator can sleep and retry
            logger.warning("fetch_network_error", url=url, error=str(exc))
            raise

        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type:
            logger.debug("skip_non_html", url=url, content_type=content_type)
            return None

        if resp.status_code >= 400:
            logger.info("http_error_status", url=url, status=resp.status_code)
            return None

        final_url = normalize_url(str(resp.url))
        soup = BeautifulSoup(resp.text, "lxml")

        title_tag = soup.find("title")
        title = clean_text(title_tag.get_text()) if title_tag else final_url

        content = self._extract_text(soup)
        links = self._extract_links(soup, final_url)
        meta = self._parse_meta(soup)
        canonical = extract_canonical_url(soup, final_url)
        json_ld = extract_json_ld(soup)
        c_hash = hash_content(content)
        language = detect_language(content[:2000])

        return CrawledPage(
            url=final_url,
            title=title,
            content=content,
            links=links,
            status_code=resp.status_code,
            meta=meta,
            content_hash=c_hash,
            language=language,
            json_ld=json_ld,
            canonical_url=canonical,
            crawled_at=datetime.utcnow(),
            depth=depth,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def crawl(
        self,
        start_url: str,
        max_depth: Optional[int] = None,
        max_pages: Optional[int] = None,
        follow_external: Optional[bool] = None,
    ) -> list[CrawledPage]:
        """
        BFS-crawl starting from *start_url*.

        Args:
            start_url:       Seed URL.  Will be normalised before use.
            max_depth:       Override config ``max_depth``.
            max_pages:       Override config ``max_pages``.
            follow_external: Override config ``follow_external_links``.

        Returns:
            Ordered list of ``CrawledPage`` objects (insertion = crawl order).
        """
        max_depth = max_depth if max_depth is not None else self._cfg.max_depth
        max_pages = max_pages if max_pages is not None else self._cfg.max_pages
        follow_ext = follow_external if follow_external is not None else self._cfg.follow_external_links

        start_url = normalize_url(start_url)
        visited: set[str] = set()
        seen_hashes: set[str] = set()
        pages: list[CrawledPage] = []
        # BFS queue: (url, depth)
        queue: deque[tuple[str, int]] = deque([(start_url, 0)])

        limits = httpx.Limits(
            max_connections=self._cfg.max_connections,
            max_keepalive_connections=self._cfg.max_keepalive_connections,
        )
        semaphore = asyncio.Semaphore(self._cfg.concurrency)

        async with httpx.AsyncClient(
            headers=self._request_headers,
            limits=limits,
            max_redirects=self._cfg.max_redirects,
        ) as client:
            robots = RobotsCache(self._cfg.user_agent)

            # ---- Optional sitemap seeding ----
            if self._cfg.use_sitemap:
                sitemap_parser = SitemapParser(client)
                sitemap_urls = await sitemap_parser.discover(start_url)
                for surl in sitemap_urls[: max_pages * 2]:
                    norm = normalize_url(surl)
                    if norm not in visited:
                        queue.append((norm, 1))

            # ---- BFS main loop ----
            async def _process(url: str, depth: int) -> None:
                """Fetch one URL and enqueue its links."""
                async with semaphore:
                    page = await self._fetch(client, url, depth, robots)
                if page is None:
                    return

                # Content-level deduplication
                if page.content_hash:
                    if page.content_hash in seen_hashes:
                        logger.debug("duplicate_skipped", url=url)
                        return
                    seen_hashes.add(page.content_hash)

                pages.append(page)
                logger.info(
                    "page_crawled",
                    url=page.url,
                    depth=depth,
                    status=page.status_code,
                    lang=page.language,
                    total=len(pages),
                )

                if depth < max_depth:
                    for link in page.links:
                        if link not in visited:
                            if follow_ext or is_same_domain(start_url, link):
                                queue.append((link, depth + 1))

            while queue and len(pages) < max_pages:
                # Drain up to `concurrency` items from the queue at once
                batch: list[tuple[str, int]] = []
                while queue and len(batch) < self._cfg.concurrency:
                    url, depth = queue.popleft()
                    if url not in visited and depth <= max_depth:
                        visited.add(url)
                        batch.append((url, depth))

                if not batch:
                    break

                tasks = [
                    asyncio.create_task(_process(url, depth))
                    for url, depth in batch
                ]
                await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(
            "crawl_complete",
            start_url=start_url,
            total_pages=len(pages),
            total_visited=len(visited),
        )
        return pages
