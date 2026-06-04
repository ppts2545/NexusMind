"""Site adapter for BBC News (bbc.com / bbc.co.uk)."""
from __future__ import annotations

from .base import BaseSiteAdapter


class BBCAdapter(BaseSiteAdapter):
    """
    Adapter for BBC News articles.

    BBC uses a component-based layout where article text lives inside
    ``[data-component="text-block"]`` elements, grouped under
    ``.article__body-content``.
    """

    domains = ["bbc.com", "bbc.co.uk"]

    content_selectors = [
        ".article__body-content",
        '[data-component="text-block"]',
        ".story-body__inner",
        "article",
    ]

    author_selectors = [
        ".byline__name",
        ".author-name",
        ".contributor-name",
    ]

    date_attrs = [
        ("property", "article:published_time"),
        ("name", "datePublished"),
    ]
