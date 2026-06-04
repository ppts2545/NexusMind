"""
Shared utility functions for the crawler package.

Covers: URL normalisation, content hashing, language detection,
JSON-LD extraction, text cleaning, and the async retry decorator.
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import re
import time
from typing import Any, Callable, Optional, TypeVar
from urllib.parse import urljoin, urlparse, urlunparse, urlencode, parse_qs

import structlog
from bs4 import BeautifulSoup

try:
    from langdetect import detect, LangDetectException  # type: ignore[import]
    _LANGDETECT_AVAILABLE = True
except ImportError:
    _LANGDETECT_AVAILABLE = False

F = TypeVar("F", bound=Callable[..., Any])

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog bound logger for the given module name."""
    return structlog.get_logger(name)


# ---------------------------------------------------------------------------
# URL utilities
# ---------------------------------------------------------------------------

def normalize_url(url: str) -> str:
    """
    Canonicalise a URL for consistent deduplication.

    Steps:
    - Remove URL fragment (#anchor).
    - Alphabetically sort query parameters.
    - Strip trailing slash from non-root paths.
    - Lowercase the scheme and host.
    """
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return url

    # Lowercase scheme + netloc
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Remove fragment
    fragment = ""

    # Stable query string (sorted key order)
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)
        sorted_query = urlencode(sorted(params.items()), doseq=True)
    else:
        sorted_query = ""

    # Trim trailing slash except for bare root
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    return urlunparse((scheme, netloc, path, parsed.params, sorted_query, fragment))


def extract_canonical_url(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """
    Return the canonical URL declared on the page, or ``None``.

    Checks ``<link rel="canonical">`` first, then ``og:url``.
    """
    link_tag = soup.find("link", rel="canonical")
    if link_tag and link_tag.get("href"):
        return urljoin(base_url, str(link_tag["href"]).strip())

    og_url = soup.find("meta", property="og:url")
    if og_url and og_url.get("content"):
        return str(og_url["content"]).strip()

    return None


def is_valid_url(url: str) -> bool:
    """Return ``True`` if *url* has an HTTP/HTTPS scheme and a non-empty host."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except ValueError:
        return False


def is_same_domain(url_a: str, url_b: str) -> bool:
    """Return ``True`` if both URLs share the same ``netloc``."""
    return urlparse(url_a).netloc.lower() == urlparse(url_b).netloc.lower()


# ---------------------------------------------------------------------------
# Content utilities
# ---------------------------------------------------------------------------

def hash_content(content: str) -> str:
    """Return the SHA-256 hex digest of *content* encoded as UTF-8."""
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()


def clean_text(text: str) -> str:
    """Collapse all whitespace runs to a single space and strip the result."""
    return re.sub(r"\s+", " ", text).strip()


def count_words(text: str) -> int:
    """Return a simple whitespace-split word count."""
    return len(text.split())


def detect_language(text: str) -> Optional[str]:
    """
    Detect the dominant language of *text*.

    Returns an ISO 639-1 code (e.g. ``"en"``) or ``None`` when detection is
    unavailable or the sample is too short.
    """
    if not _LANGDETECT_AVAILABLE:
        return None
    if len(text.strip()) < 20:
        return None
    try:
        return detect(text)
    except Exception:
        return None


def extract_json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """
    Extract all ``application/ld+json`` structured-data blocks from a page.

    Returns a flat list of dicts (handles both single objects and arrays).
    """
    results: list[dict[str, Any]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            raw = (script.string or "").strip()
            if not raw:
                continue
            data = json.loads(raw)
            if isinstance(data, list):
                results.extend(d for d in data if isinstance(d, dict))
            elif isinstance(data, dict):
                results.append(data)
        except (json.JSONDecodeError, TypeError):
            continue
    return results


# ---------------------------------------------------------------------------
# Async retry decorator
# ---------------------------------------------------------------------------

def retry_async(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """
    Decorator that retries an ``async`` function with exponential back-off.

    A small ±10 % jitter is added to each sleep to avoid thundering-herd
    problems when many coroutines retry at the same time.

    Args:
        max_retries: Number of *additional* attempts after the first failure.
        base_delay: Sleep (seconds) before the first retry.
        max_delay: Upper cap on the sleep duration.
        backoff_factor: Multiplier applied to *delay* after each attempt.
        exceptions: Only retry on these exception types.
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            _logger = get_logger(func.__module__)
            delay = base_delay
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_retries:
                        raise
                    # Small ±10 % jitter
                    jitter = delay * 0.1 * (2.0 * (time.time() % 1.0) - 1.0)
                    sleep_for = min(delay + jitter, max_delay)
                    _logger.warning(
                        "retry_scheduled",
                        func=func.__qualname__,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        sleep=round(sleep_for, 2),
                        error=str(exc),
                    )
                    await asyncio.sleep(sleep_for)
                    delay = min(delay * backoff_factor, max_delay)

        return wrapper  # type: ignore[return-value]
    return decorator
