"""Site adapter for CNN (cnn.com)."""
from __future__ import annotations

from .base import BaseSiteAdapter


class CNNAdapter(BaseSiteAdapter):
    """
    Adapter for CNN articles.

    CNN's article body is split across multiple ``<p>`` paragraphs inside
    ``.article__content``; older pages use ``.zn-body__paragraph``.
    """

    domains = ["cnn.com"]

    content_selectors = [
        ".article__content",
        ".zn-body__paragraph",
        ".l-container",
        "article",
    ]

    author_selectors = [
        ".byline__name",
        ".metadata__byline__author",
        ".author__name",
    ]

    date_attrs = [
        ("property", "og:article:published_time"),
        ("property", "article:published_time"),
        ("name", "pubdate"),
        ("name", "date"),
    ]
