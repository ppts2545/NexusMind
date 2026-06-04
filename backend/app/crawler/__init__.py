"""
NexusMind crawler package.

Exposes the primary classes and data models at the package level for
convenient imports::

    from app.crawler import WebCrawler, ArticleScraper, FeedScraper
    from app.crawler import CrawlerConfig
    from app.crawler import CrawledPage, Article, FeedItem, PageMeta
"""
from .config import CrawlerConfig
from .crawler import RobotsCache, SitemapParser, WebCrawler
from .models import Article, CrawledPage, FeedItem, PageMeta
from .scraper import ArticleScraper, FeedScraper

__all__ = [
    # Config
    "CrawlerConfig",
    # Crawler internals
    "RobotsCache",
    "SitemapParser",
    "WebCrawler",
    # Scrapers
    "ArticleScraper",
    "FeedScraper",
    # Data models
    "CrawledPage",
    "PageMeta",
    "Article",
    "FeedItem",
]
