"""Unit tests for the recursive chunker."""
from __future__ import annotations

import uuid

import pytest

from app.domain.document import CleanDocument, SourceType
from app.rag.chunker import RecursiveChunker


def make_clean_doc(text: str) -> CleanDocument:
    return CleanDocument(
        source_document_id=uuid.uuid4(),
        source="test",
        source_type=SourceType.API,
        title="Test",
        text=text,
        word_count=len(text.split()),
    )


class TestRecursiveChunker:
    def test_short_text_single_chunk(self):
        chunker = RecursiveChunker(chunk_size=512, chunk_overlap=64)
        doc = make_clean_doc("Hello world. This is a short text.")
        chunks = chunker.chunk(doc)
        assert len(chunks) == 1
        assert chunks[0].chunk_index == 0

    def test_long_text_multiple_chunks(self, sample_text):
        chunker = RecursiveChunker(chunk_size=100, chunk_overlap=10)
        doc = make_clean_doc(sample_text * 5)
        chunks = chunker.chunk(doc)
        assert len(chunks) > 1

    def test_chunk_size_respected(self, sample_text):
        chunk_size = 200
        chunker = RecursiveChunker(chunk_size=chunk_size, chunk_overlap=20)
        doc = make_clean_doc(sample_text * 5)
        chunks = chunker.chunk(doc)
        for chunk in chunks:
            assert len(chunk.content) <= chunk_size + 50  # allow some tolerance

    def test_metadata_preserved(self, sample_text):
        chunker = RecursiveChunker(chunk_size=200, chunk_overlap=20)
        doc = make_clean_doc(sample_text)
        chunks = chunker.chunk(doc)
        for chunk in chunks:
            assert "source" in chunk.metadata
            assert "title" in chunk.metadata

    def test_document_id_on_chunks(self, sample_text):
        chunker = RecursiveChunker(chunk_size=200, chunk_overlap=20)
        doc = make_clean_doc(sample_text)
        chunks = chunker.chunk(doc)
        for chunk in chunks:
            assert chunk.document_id == doc.source_document_id

    def test_approx_token_count(self):
        chunker = RecursiveChunker()
        doc = make_clean_doc("a " * 100)
        chunks = chunker.chunk(doc)
        for chunk in chunks:
            assert chunk.token_count > 0
