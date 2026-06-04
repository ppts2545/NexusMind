"""Site adapter for Medium (medium.com and custom Medium domains)."""
from __future__ import annotations

from typing import Any, Optional

from bs4 import BeautifulSoup

from .base import BaseSiteAdapter
from ..utils import clean_text


class MediumAdapter(BaseSiteAdapter):
    """
    Adapter for Medium articles.

    Medium renders content inside ``<section>`` tags with ``data-field="body"``
    and author names in ``.pw-author-name``.  The clap/reaction section and
    sidebars must be stripped to avoid polluting the article text.
    """

    domains = ["medium.com"]

    content_selectors = [
        'section[data-field="body"]',
        ".story-body",
        "article",
    ]

    author_selectors = [
        ".pw-author-name",
        ".author-name",
        'a[rel="author"]',
    ]

    date_attrs = [
        ("property", "article:published_time"),
        ("name", "parsely-pub-date"),
    ]

    # Medium-specific noise: reaction bars, paywall overlays, membership CTAs
    noise_tags = BaseSiteAdapter.noise_tags + ["svg"]

    def extract_content(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Override to also strip Medium's paywall / membership overlay divs
        before extracting text.
        """
        for div in soup.select(".meteredContent, .overlay, .branch-journey-wrapper"):
            div.decompose()
        return super().extract_content(soup)
