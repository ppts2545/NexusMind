"""
Data models for the crawler package.

All models are plain dataclasses — no ORM or Pydantic dependency — so they
can be serialised to dict/JSON easily and passed to any downstream pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class PageMeta:
    """
    Metadata extracted from a page's <head> section.

    Covers standard meta tags, OpenGraph properties, and article-specific
    publishing information.
    """

    description: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    og_title: Optional[str] = None
    og_image: Optional[str] = None
    keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "author": self.author,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "og_title": self.og_title,
            "og_image": self.og_image,
            "keywords": self.keywords,
        }


@dataclass
class CrawledPage:
    """
    Represents a single fetched and parsed HTML page.

    ``content_hash`` (SHA-256) is used for duplicate detection.
    ``json_ld`` holds all structured-data blocks found on the page.
    """

    url: str
    title: str
    content: str
    links: list[str] = field(default_factory=list)
    status_code: int = 200
    meta: PageMeta = field(default_factory=PageMeta)
    content_hash: Optional[str] = None
    language: Optional[str] = None
    json_ld: list[dict[str, Any]] = field(default_factory=list)
    canonical_url: Optional[str] = None
    crawled_at: datetime = field(default_factory=datetime.utcnow)
    depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "links": self.links,
            "status_code": self.status_code,
            "meta": self.meta.to_dict(),
            "content_hash": self.content_hash,
            "language": self.language,
            "json_ld": self.json_ld,
            "canonical_url": self.canonical_url,
            "crawled_at": self.crawled_at.isoformat(),
            "depth": self.depth,
        }


@dataclass
class Article:
    """
    A fully extracted article with structured metadata.

    Produced by ``ArticleScraper.scrape()``.  ``word_count`` reflects the
    cleaned body text; ``images`` lists all ``<img src>`` values found inside
    the main content container.
    """

    url: str
    title: str
    content: str
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    description: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    word_count: int = 0
    language: Optional[str] = None
    content_hash: Optional[str] = None
    source_domain: Optional[str] = None   # e.g. "thairath.co.th"
    embedding_id: Optional[str] = None    # vector DB reference after embedding
    crawl_time: Optional[float] = None    # seconds taken to fetch + parse
    scraped_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "author": self.author,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "description": self.description,
            "tags": self.tags,
            "images": self.images,
            "word_count": self.word_count,
            "language": self.language,
            "content_hash": self.content_hash,
            "source_domain": self.source_domain,
            "embedding_id": self.embedding_id,
            "crawl_time": self.crawl_time,
            "scraped_at": self.scraped_at.isoformat(),
        }


@dataclass
class FeedItem:
    """
    A single item parsed from an RSS or Atom feed.

    Produced by ``FeedScraper.scrape()``.
    """

    url: str
    title: str
    summary: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "summary": self.summary,
            "author": self.author,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "tags": self.tags,
        }
