"""Text cleaning — HTML removal, Unicode normalization, whitespace."""
from __future__ import annotations

import re
import unicodedata

from app.domain.document import CleanDocument, Document


class TextCleaner:
    """
    Converts raw ``Document`` objects into ``CleanDocument`` objects.

    Pipeline:
        1. Strip residual HTML tags
        2. Fix Unicode mojibake (ftfy)
        3. Normalize Unicode (NFC)
        4. Collapse whitespace
        5. Count words
    """

    _HTML_TAG = re.compile(r"<[^>]+>")
    _MULTI_NEWLINE = re.compile(r"\n{3,}")
    _MULTI_SPACE = re.compile(r" {2,}")
    _CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

    def clean(self, doc: Document) -> CleanDocument:
        text = self._clean_text(doc.text)
        word_count = len(text.split())
        return CleanDocument(
            source_document_id=doc.id,
            source=doc.source,
            source_type=doc.source_type,
            url=doc.url,
            title=self._clean_text(doc.title),
            text=text,
            language=doc.language,
            word_count=word_count,
            metadata=doc.metadata,
        )

    def clean_batch(self, docs: list[Document]) -> list[CleanDocument]:
        return [self.clean(d) for d in docs]

    def _clean_text(self, text: str) -> str:
        # Fix Unicode mojibake (ftfy is a soft dep — skip if unavailable)
        try:
            import ftfy  # type: ignore[import]
            text = ftfy.fix_text(text)
        except ImportError:
            pass

        # Strip HTML
        text = self._HTML_TAG.sub(" ", text)

        # Remove control characters
        text = self._CONTROL_CHARS.sub("", text)

        # NFC normalization
        text = unicodedata.normalize("NFC", text)

        # Collapse whitespace
        text = self._MULTI_NEWLINE.sub("\n\n", text)
        text = self._MULTI_SPACE.sub(" ", text)

        return text.strip()
