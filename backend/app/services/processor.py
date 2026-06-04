import hashlib
import re
from dataclasses import dataclass

from langdetect import detect

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class Chunk:
    index: int
    content: str
    token_count: int
    meta: dict


class DocumentProcessor:
    def content_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def detect_language(self, text: str) -> str:
        try:
            return detect(text[:2000])
        except Exception:
            return "unknown"

    def clean_text(self, text: str) -> str:
        text = re.sub(r"\r\n|\r", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()

    def chunk_text(self, text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[Chunk]:
        chunk_size = chunk_size or settings.CHUNK_SIZE
        overlap = overlap or settings.CHUNK_OVERLAP

        words = text.split()
        if not words:
            return []

        chunks: list[Chunk] = []
        start = 0
        idx = 0

        while start < len(words):
            end = min(start + chunk_size, len(words))
            chunk_words = words[start:end]
            content = " ".join(chunk_words)
            chunks.append(
                Chunk(
                    index=idx,
                    content=content,
                    token_count=len(chunk_words),
                    meta={"start_word": start, "end_word": end},
                )
            )
            if end >= len(words):
                break
            start = end - overlap
            idx += 1

        return chunks

    def process(self, raw_text: str, meta: dict | None = None) -> tuple[str, list[Chunk], str, str]:
        """Returns (cleaned_text, chunks, language, content_hash)."""
        cleaned = self.clean_text(raw_text)
        language = self.detect_language(cleaned)
        content_hash = self.content_hash(cleaned)
        chunks = self.chunk_text(cleaned)
        logger.info("document_processed", language=language, chunks=len(chunks), hash=content_hash[:8])
        return cleaned, chunks, language, content_hash
