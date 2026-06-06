"""Recursive text chunker with metadata preservation."""
from __future__ import annotations

import re
from uuid import UUID

from app.domain.document import CleanDocument, TextChunk


class RecursiveChunker:
    """
    Recursive character-based chunker — splits on paragraphs, then sentences,
    then words, falling back to characters as needed.

    Preserves document metadata on every chunk for downstream traceability.
    """

    _SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64) -> None:
        self._size = chunk_size
        self._overlap = chunk_overlap

    def chunk(self, doc: CleanDocument) -> list[TextChunk]:
        raw_chunks = self._split(doc.text, self._SEPARATORS)
        chunks: list[TextChunk] = []

        for i, text in enumerate(raw_chunks):
            if not text.strip():
                continue
            chunks.append(
                TextChunk(
                    document_id=doc.source_document_id,
                    chunk_index=i,
                    content=text.strip(),
                    token_count=self._approx_tokens(text),
                    metadata={
                        "source": doc.source,
                        "source_type": doc.source_type,
                        "url": doc.url,
                        "title": doc.title,
                        "language": doc.language,
                        "chunk_index": i,
                        **{k: v for k, v in doc.metadata.items() if isinstance(v, (str, int, float, bool))},
                    },
                )
            )

        return chunks

    def chunk_batch(self, docs: list[CleanDocument]) -> list[TextChunk]:
        result: list[TextChunk] = []
        for doc in docs:
            result.extend(self.chunk(doc))
        return result

    # ── Internal ──────────────────────────────────────────────────────────────

    def _split(self, text: str, separators: list[str]) -> list[str]:
        if not separators:
            return self._fixed_split(text)

        sep = separators[0]
        splits = text.split(sep) if sep else list(text)

        good: list[str] = []
        current = ""

        for s in splits:
            candidate = (current + sep + s) if current else s
            if len(candidate) <= self._size:
                current = candidate
            else:
                if current:
                    good.append(current)
                # If a single split is still too big, recurse into smaller seps
                if len(s) > self._size:
                    good.extend(self._split(s, separators[1:]))
                    current = ""
                else:
                    current = s

        if current:
            good.append(current)

        # Add overlap between consecutive chunks
        if self._overlap > 0:
            good = self._apply_overlap(good, sep)

        return good

    def _apply_overlap(self, chunks: list[str], sep: str) -> list[str]:
        if len(chunks) <= 1:
            return chunks
        result: list[str] = [chunks[0]]
        for i in range(1, len(chunks)):
            prev = chunks[i - 1]
            overlap_text = prev[-self._overlap:] if len(prev) > self._overlap else prev
            merged = overlap_text + sep + chunks[i]
            if len(merged) <= self._size + self._overlap:
                result.append(merged)
            else:
                result.append(chunks[i])
        return result

    def _fixed_split(self, text: str) -> list[str]:
        return [text[i: i + self._size] for i in range(0, len(text), self._size - self._overlap)]

    @staticmethod
    def _approx_tokens(text: str) -> int:
        return max(1, len(text) // 4)
