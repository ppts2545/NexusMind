"""Common Crawl source — reads WARC files and emits Document objects.

Designed as a thin wrapper that can hand off to datatrove for TB-scale
processing.  At small scale it reads WARC files directly via warcio.
"""
from __future__ import annotations

import asyncio
import gzip
import io

from app.domain.document import Document, SourceType
from app.sources.base import BaseSource


def _parse_warc_bytes(data: bytes) -> list[tuple[str, str, str]]:
    """
    Parse a WARC file (gzip or plain) and return (url, title, text) tuples.
    Runs in a thread pool — CPU-bound.
    """
    from warcio.archiveiterator import ArchiveIterator  # type: ignore[import]
    from bs4 import BeautifulSoup

    buf = io.BytesIO(data)
    results: list[tuple[str, str, str]] = []

    for record in ArchiveIterator(buf):
        if record.rec_type != "response":
            continue
        content_type = record.http_headers.get_header("Content-Type", "")
        if "text/html" not in content_type:
            continue

        url = record.rec_headers.get_header("WARC-Target-URI", "")
        try:
            html = record.content_stream().read().decode("utf-8", errors="replace")
        except Exception:
            continue

        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else url
        text = " ".join(soup.get_text(separator=" ").split())

        if len(text) > 100:
            results.append((url, title, text))

    return results


class CommonCrawlSource(BaseSource):
    """
    Load documents from Common Crawl WARC files.

    Accepts either local WARC file paths or HTTP(S) URLs to WARC files
    (e.g., from https://data.commoncrawl.org/).

    For TB-scale processing, replace this with a datatrove pipeline:

        from datatrove.pipeline.readers import WarcReader
        from datatrove.pipeline.filters import LanguageFilter, GopherQualityFilter
        from datatrove.pipeline.writers import JsonlWriter

        pipeline = [WarcReader(...), LanguageFilter(), GopherQualityFilter(), JsonlWriter()]
    """

    def __init__(self, warc_paths: list[str], max_docs_per_file: int | None = None) -> None:
        self._warc_paths = warc_paths
        self._max_docs = max_docs_per_file

    async def load(self) -> list[Document]:
        documents: list[Document] = []
        for path in self._warc_paths:
            data = await self._fetch(path)
            records = await asyncio.to_thread(_parse_warc_bytes, data)
            if self._max_docs:
                records = records[: self._max_docs]
            for url, title, text in records:
                documents.append(
                    Document(
                        source=f"common_crawl:{path}",
                        source_type=SourceType.COMMON_CRAWL,
                        url=url,
                        title=title,
                        text=text,
                    )
                )
        return documents

    async def stream(self):
        for path in self._warc_paths:
            data = await self._fetch(path)
            records = await asyncio.to_thread(_parse_warc_bytes, data)
            count = 0
            for url, title, text in records:
                if self._max_docs and count >= self._max_docs:
                    break
                yield Document(
                    source=f"common_crawl:{path}",
                    source_type=SourceType.COMMON_CRAWL,
                    url=url,
                    title=title,
                    text=text,
                )
                count += 1

    async def _fetch(self, path: str) -> bytes:
        if path.startswith("http"):
            import httpx
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(path)
                resp.raise_for_status()
                data = resp.content
        else:
            import aiofiles  # type: ignore[import]
            async with aiofiles.open(path, "rb") as f:
                data = await f.read()

        # Auto-decompress if gzipped
        if path.endswith(".gz") or data[:2] == b"\x1f\x8b":
            data = await asyncio.to_thread(gzip.decompress, data)

        return data
