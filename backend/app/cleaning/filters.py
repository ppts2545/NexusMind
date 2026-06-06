"""Quality, language, spam, and PII filters for the cleaning pipeline."""
from __future__ import annotations

import re

from app.domain.document import CleanDocument


class LanguageFilter:
    """Keep only documents in the allowed languages."""

    def __init__(self, languages: list[str] | None = None) -> None:
        self._languages = set(languages or ["en"])

    def passes(self, doc: CleanDocument) -> bool:
        return doc.language in self._languages


class QualityFilter:
    """
    Heuristic quality filter inspired by C4 / Gopher rules.

    Checks:
    - Minimum word count
    - Maximum repetition ratio (repeated lines / total lines)
    - Minimum average word length
    - No excessive punctuation
    """

    def __init__(
        self,
        min_words: int = 50,
        max_repetition_ratio: float = 0.3,
        min_avg_word_len: float = 3.0,
        max_symbol_word_ratio: float = 0.1,
    ) -> None:
        self._min_words = min_words
        self._max_rep = max_repetition_ratio
        self._min_avg_wl = min_avg_word_len
        self._max_sym = max_symbol_word_ratio

    def passes(self, doc: CleanDocument) -> bool:
        text = doc.text
        words = text.split()

        if len(words) < self._min_words:
            return False

        # Repetition ratio
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if lines:
            unique_lines = len(set(lines))
            rep_ratio = 1 - (unique_lines / len(lines))
            if rep_ratio > self._max_rep:
                return False

        # Average word length
        avg_wl = sum(len(w) for w in words) / len(words)
        if avg_wl < self._min_avg_wl:
            return False

        # Symbol/word ratio (hash, pipe, etc.)
        symbol_count = sum(1 for c in text if c in "#|<>{}[]\\")
        if symbol_count / len(words) > self._max_sym:
            return False

        return True

    def score(self, doc: CleanDocument) -> float:
        """Return a quality score between 0.0 and 1.0."""
        text = doc.text
        words = text.split()
        if not words:
            return 0.0

        scores: list[float] = []

        # Word count score (logarithmic)
        import math
        scores.append(min(1.0, math.log(len(words) + 1) / math.log(500)))

        # Repetition score
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if lines:
            rep_ratio = 1 - len(set(lines)) / len(lines)
            scores.append(1 - rep_ratio)

        # Avg word length score
        avg_wl = sum(len(w) for w in words) / len(words)
        scores.append(min(1.0, avg_wl / 6))

        return sum(scores) / len(scores)


class SpamFilter:
    """Very light spam/boilerplate filter based on keyword density."""

    _SPAM_PATTERNS = re.compile(
        r"(click here|subscribe now|buy now|limited time offer|"
        r"100% free|make money|work from home|congratulations you|"
        r"you have been selected)",
        re.IGNORECASE,
    )

    def __init__(self, max_spam_density: float = 0.02) -> None:
        self._max_density = max_spam_density

    def passes(self, doc: CleanDocument) -> bool:
        matches = self._SPAM_PATTERNS.findall(doc.text)
        word_count = max(len(doc.text.split()), 1)
        return len(matches) / word_count <= self._max_density


class PIIFilter:
    """
    PII detection hook — marks documents containing potential PII.

    Production implementations should replace this with a proper NER model
    (e.g., spaCy, Presidio) or a dedicated PII detection service.
    """

    _EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    _PHONE = re.compile(r"\b(\+\d{1,3}[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")
    _SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

    def has_pii(self, doc: CleanDocument) -> bool:
        text = doc.text
        return bool(self._EMAIL.search(text) or self._PHONE.search(text) or self._SSN.search(text))


class CleaningPipeline:
    """
    Runs all filters in sequence.

    Usage::

        pipeline = CleaningPipeline()
        clean_docs = pipeline.run(dirty_docs)
    """

    def __init__(
        self,
        languages: list[str] | None = None,
        min_words: int = 50,
        max_repetition_ratio: float = 0.3,
        remove_pii: bool = False,
    ) -> None:
        self._lang = LanguageFilter(languages)
        self._quality = QualityFilter(min_words=min_words, max_repetition_ratio=max_repetition_ratio)
        self._spam = SpamFilter()
        self._pii = PIIFilter()
        self._remove_pii = remove_pii

    def run(self, docs: list[CleanDocument]) -> list[CleanDocument]:
        results: list[CleanDocument] = []
        for doc in docs:
            if not self._lang.passes(doc):
                continue
            if not self._quality.passes(doc):
                continue
            if not self._spam.passes(doc):
                continue
            if self._remove_pii and self._pii.has_pii(doc):
                continue
            doc = doc.model_copy(update={"quality_score": self._quality.score(doc)})
            results.append(doc)
        return results
