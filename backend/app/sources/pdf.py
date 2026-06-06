"""PDF source — extracts text from local files or URLs using pypdf."""
from __future__ import annotations

import asyncio
import io
from pathlib import Path

from app.domain.document import Document, SourceType
from app.sources.base import BaseSource


def _extract_pdf_bytes(data: bytes) -> tuple[str, dict]:
    """Extract text and metadata from raw PDF bytes (runs in thread pool)."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages_text: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages_text.append(text)

    meta = {}
    if reader.metadata:
        raw = reader.metadata
        meta = {
            "author": getattr(raw, "author", None),
            "creator": getattr(raw, "creator", None),
            "producer": getattr(raw, "producer", None),
            "subject": getattr(raw, "subject", None),
            "creation_date": str(getattr(raw, "creation_date", "") or ""),
        }

    return "\n\n".join(pages_text), meta


class PDFSource(BaseSource):
    """Load documents from a list of PDF file paths or HTTP URLs."""

    def __init__(self, sources: list[str]) -> None:
        self._sources = sources   # file paths or http(s) URLs

    async def load(self) -> list[Document]:
        documents: list[Document] = []
        for src in self._sources:
            try:
                data, title = await self._fetch(src)
                text, meta = await asyncio.to_thread(_extract_pdf_bytes, data)
                documents.append(
                    Document(
                        source=src,
                        source_type=SourceType.PDF,
                        url=src if src.startswith("http") else None,
                        title=title,
                        text=text,
                        metadata=meta,
                    )
                )
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("pdf_load_failed", extra={"source": src, "error": str(exc)})
        return documents

    async def _fetch(self, src: str) -> tuple[bytes, str]:
        if src.startswith("http"):
            import httpx
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                resp = await client.get(src)
                resp.raise_for_status()
                title = Path(src.split("?")[0]).stem or src
                return resp.content, title
        else:
            path = Path(src)
            data = await asyncio.to_thread(path.read_bytes)
            return data, path.stem
