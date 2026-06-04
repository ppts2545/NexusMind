"""
BaseSiteAdapter and AdapterRegistry.

Each site adapter overrides only the parts that differ from the defaults —
content selectors, date meta-tag names, author selectors, etc.  The Core
Crawler and ArticleScraper stay unchanged; adapters plug in via the registry.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..utils import clean_text, get_logger

logger = get_logger(__name__)

# Defaults shared by every adapter that does not override them
_DEFAULT_CONTENT_SELECTORS: list[str] = [
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

_DEFAULT_AUTHOR_SELECTORS: list[str] = [
    ".author",
    ".byline",
    '[rel="author"]',
    ".post-author",
    ".entry-author",
]

_DEFAULT_DATE_ATTRS: list[tuple[str, str]] = [
    ("property", "article:published_time"),
    ("property", "dateCreated"),
    ("name", "datePublished"),
    ("name", "publish-date"),
    ("name", "date"),
    ("name", "DC.date"),
]

_NOISE_TAGS: list[str] = [
    "script", "style", "nav", "footer", "header",
    "aside", "noscript", "figure", "form",
]


class BaseSiteAdapter:
    """
    Default site adapter — used when no domain-specific adapter is registered.

    Subclasses override class-level attributes to customise behaviour for a
    specific site.  Override ``extract_content``, ``extract_author``, or
    ``extract_published_at`` for logic that cannot be expressed as a simple
    selector/attribute list.

    Example::

        class BBCAdapter(BaseSiteAdapter):
            domains = ["bbc.com", "bbc.co.uk"]
            content_selectors = [".article__body-content"]
            author_selectors  = [".byline__name"]
    """

    # Override in subclass -----------------------------------------------
    domains: list[str] = []
    content_selectors: list[str] = _DEFAULT_CONTENT_SELECTORS
    author_selectors: list[str] = _DEFAULT_AUTHOR_SELECTORS
    date_attrs: list[tuple[str, str]] = _DEFAULT_DATE_ATTRS
    noise_tags: list[str] = _NOISE_TAGS
    # ---------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    def extract_content(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Find the main content container and return cleaned text.

        Tries ``content_selectors`` in order; returns ``None`` when none match
        so ``ArticleScraper`` can fall back to ``<body>``.
        """
        for selector in self.content_selectors:
            el = soup.select_one(selector)
            if el:
                return self._clean(el)
        return None

    def _clean(self, container: Any) -> str:
        """Strip noise tags and return whitespace-collapsed text."""
        for tag in container.find_all(self.noise_tags):
            tag.decompose()
        return clean_text(container.get_text(separator=" "))

    # ------------------------------------------------------------------
    # Author
    # ------------------------------------------------------------------

    def extract_author(
        self,
        soup: BeautifulSoup,
        json_ld: list[dict[str, Any]],
    ) -> Optional[str]:
        """Extract author from JSON-LD, meta, or DOM selectors."""
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

        meta = soup.find("meta", attrs={"name": "author"})
        if meta and meta.get("content"):
            return str(meta["content"]).strip()

        for selector in self.author_selectors:
            el = soup.select_one(selector)
            if el:
                text = clean_text(el.get_text())
                if text:
                    return text

        return None

    # ------------------------------------------------------------------
    # Publication date
    # ------------------------------------------------------------------

    def extract_published_at(
        self,
        soup: BeautifulSoup,
        json_ld: list[dict[str, Any]],
    ) -> Optional[datetime]:
        """Parse publication date from JSON-LD → meta attrs → <time>."""
        date_str: Optional[str] = None

        for item in json_ld:
            date_str = item.get("datePublished") or item.get("dateCreated")
            if date_str:
                break

        if not date_str:
            for attr_name, attr_value in self.date_attrs:
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


# ---------------------------------------------------------------------------
# AdapterRegistry
# ---------------------------------------------------------------------------

class AdapterRegistry:
    """
    Map hostnames to their ``BaseSiteAdapter`` instances.

    Lookup strips ``www.`` so ``www.bbc.com`` and ``bbc.com`` both resolve to
    the same adapter.  Falls back to a default ``BaseSiteAdapter`` instance
    when no match is found.
    """

    def __init__(self, adapters: list[BaseSiteAdapter]) -> None:
        self._map: dict[str, BaseSiteAdapter] = {}
        self._default = BaseSiteAdapter()
        for adapter in adapters:
            for domain in adapter.domains:
                self._map[domain.lower().lstrip("www.")] = adapter
                self._map[f"www.{domain.lower().lstrip('www.')}"] = adapter

    def get(self, url: str) -> BaseSiteAdapter:
        """Return the adapter for *url*'s domain, or the default adapter."""
        host = urlparse(url).netloc.lower()
        bare = host.lstrip("www.")
        adapter = self._map.get(host) or self._map.get(bare) or self._default
        if adapter is not self._default:
            logger.debug("adapter_matched", url=url, adapter=type(adapter).__name__)
        return adapter

    def register(self, adapter: BaseSiteAdapter) -> None:
        """Register an adapter at runtime (e.g. from a plugin)."""
        for domain in adapter.domains:
            self._map[domain.lower().lstrip("www.")] = adapter
            self._map[f"www.{domain.lower().lstrip('www.')}"] = adapter
