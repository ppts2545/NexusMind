"""
Crawler configuration dataclass.

Decoupled from the main app settings so the crawler package can be used
standalone or embedded inside NexusMind without importing Pydantic/FastAPI.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class CrawlerConfig:
    """
    All tunable parameters for the crawler and scrapers.

    Instantiate directly for programmatic use, or call ``from_env()`` to
    populate values from environment variables (falls back to the field
    defaults when an env-var is absent).
    """

    # ------------------------------------------------------------------ HTTP
    user_agent: str = "NexusMind-Bot/1.0 (+https://github.com/nexusmind)"
    timeout: float = 30.0           # total request timeout in seconds
    connect_timeout: float = 10.0   # socket connect timeout
    max_redirects: int = 10

    # --------------------------------------------------------------- Crawling
    max_depth: int = 3
    max_pages: int = 100
    concurrency: int = 10           # max simultaneous in-flight requests
    politeness_delay: float = 1.0   # minimum seconds between requests to the same domain

    # ------------------------------------------------------------- Behaviour
    follow_external_links: bool = False
    respect_robots_txt: bool = True
    use_sitemap: bool = True        # seed extra URLs from /sitemap.xml

    # ----------------------------------------------------------------- Retry
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 60.0
    retry_backoff_factor: float = 2.0

    # --------------------------------------------------------------- Content
    min_content_length: int = 100   # chars; below this we fall back to <body>

    # ---------------------------------------------------------------- Output
    log_level: str = "INFO"

    # ------------------------------------------------------------------ Pool
    # httpx connection-pool sizes; set equal to concurrency by default
    max_connections: int = field(init=False)
    max_keepalive_connections: int = field(init=False)

    def __post_init__(self) -> None:
        self.max_connections = self.concurrency
        self.max_keepalive_connections = self.concurrency

    @classmethod
    def from_env(cls) -> "CrawlerConfig":
        """
        Build a ``CrawlerConfig`` from environment variables.

        Each field maps to ``CRAWLER_<UPPER_FIELD_NAME>``.  Missing env-vars
        fall back to the dataclass default values.
        """
        defaults = cls()
        return cls(
            user_agent=os.getenv("CRAWLER_USER_AGENT", defaults.user_agent),
            timeout=float(os.getenv("CRAWLER_TIMEOUT", defaults.timeout)),
            connect_timeout=float(os.getenv("CRAWLER_CONNECT_TIMEOUT", defaults.connect_timeout)),
            max_redirects=int(os.getenv("CRAWLER_MAX_REDIRECTS", defaults.max_redirects)),
            max_depth=int(os.getenv("CRAWLER_MAX_DEPTH", defaults.max_depth)),
            max_pages=int(os.getenv("CRAWLER_MAX_PAGES", defaults.max_pages)),
            concurrency=int(os.getenv("CRAWLER_CONCURRENCY", defaults.concurrency)),
            politeness_delay=float(os.getenv("CRAWLER_POLITENESS_DELAY", defaults.politeness_delay)),
            follow_external_links=os.getenv("CRAWLER_FOLLOW_EXTERNAL", str(defaults.follow_external_links)).lower() == "true",
            respect_robots_txt=os.getenv("CRAWLER_RESPECT_ROBOTS", str(defaults.respect_robots_txt)).lower() == "true",
            use_sitemap=os.getenv("CRAWLER_USE_SITEMAP", str(defaults.use_sitemap)).lower() == "true",
            max_retries=int(os.getenv("CRAWLER_MAX_RETRIES", defaults.max_retries)),
            retry_base_delay=float(os.getenv("CRAWLER_RETRY_BASE_DELAY", defaults.retry_base_delay)),
            retry_max_delay=float(os.getenv("CRAWLER_RETRY_MAX_DELAY", defaults.retry_max_delay)),
            retry_backoff_factor=float(os.getenv("CRAWLER_RETRY_BACKOFF_FACTOR", defaults.retry_backoff_factor)),
            min_content_length=int(os.getenv("CRAWLER_MIN_CONTENT_LENGTH", defaults.min_content_length)),
            log_level=os.getenv("CRAWLER_LOG_LEVEL", defaults.log_level),
        )
