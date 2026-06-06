"""Unit tests for the cleaning pipeline."""
from __future__ import annotations

import uuid

import pytest

from app.cleaning.cleaner import TextCleaner
from app.cleaning.filters import CleaningPipeline, QualityFilter, SpamFilter
from app.domain.document import CleanDocument, Document, SourceType


def make_clean_doc(text: str, language: str = "en") -> CleanDocument:
    return CleanDocument(
        source_document_id=uuid.uuid4(),
        source="test",
        source_type=SourceType.API,
        title="Test",
        text=text,
        language=language,
        word_count=len(text.split()),
    )


class TestTextCleaner:
    def test_strips_html(self):
        cleaner = TextCleaner()
        doc = Document(source="test", source_type=SourceType.API, title="T", text="<p>Hello <b>world</b></p>")
        clean = cleaner.clean(doc)
        assert "<p>" not in clean.text
        assert "Hello" in clean.text

    def test_collapses_whitespace(self):
        cleaner = TextCleaner()
        doc = Document(source="test", source_type=SourceType.API, title="T", text="Hello   world\n\n\n\nbye")
        clean = cleaner.clean(doc)
        assert "   " not in clean.text
        assert "\n\n\n" not in clean.text

    def test_counts_words(self):
        cleaner = TextCleaner()
        doc = Document(source="test", source_type=SourceType.API, title="T", text="one two three four five")
        clean = cleaner.clean(doc)
        assert clean.word_count == 5


class TestQualityFilter:
    def test_passes_good_text(self, sample_text):
        f = QualityFilter(min_words=10)
        doc = make_clean_doc(sample_text)
        assert f.passes(doc)

    def test_rejects_short_text(self):
        f = QualityFilter(min_words=50)
        doc = make_clean_doc("too short")
        assert not f.passes(doc)

    def test_rejects_repetitive_text(self):
        f = QualityFilter(max_repetition_ratio=0.2)
        repeated = "same line\n" * 20
        doc = make_clean_doc(repeated)
        assert not f.passes(doc)

    def test_score_between_0_and_1(self, sample_text):
        f = QualityFilter()
        doc = make_clean_doc(sample_text)
        score = f.score(doc)
        assert 0.0 <= score <= 1.0


class TestSpamFilter:
    def test_passes_clean_text(self, sample_text):
        f = SpamFilter()
        doc = make_clean_doc(sample_text)
        assert f.passes(doc)

    def test_rejects_spam(self):
        f = SpamFilter(max_spam_density=0.01)
        spam = "click here click here click here buy now " * 5
        doc = make_clean_doc(spam)
        assert not f.passes(doc)


class TestCleaningPipeline:
    def test_filters_short_docs(self):
        pipeline = CleaningPipeline(min_words=50)
        docs = [make_clean_doc("too short"), make_clean_doc("x " * 100)]
        result = pipeline.run(docs)
        assert len(result) == 1

    def test_preserves_good_docs(self, sample_text):
        pipeline = CleaningPipeline(min_words=10)
        docs = [make_clean_doc(sample_text)]
        result = pipeline.run(docs)
        assert len(result) == 1
        assert result[0].quality_score > 0
