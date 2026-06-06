"""Unit tests for source adapters."""
from __future__ import annotations

import pytest

from app.domain.document import SourceType


class TestPDFSource:
    def test_pdf_source_instantiates(self):
        from app.sources.pdf import PDFSource
        src = PDFSource(sources=[])
        assert src is not None

    @pytest.mark.asyncio
    async def test_empty_sources_returns_empty(self):
        from app.sources.pdf import PDFSource
        src = PDFSource(sources=[])
        docs = await src.load()
        assert docs == []


class TestHuggingFaceSource:
    def test_hf_source_instantiates(self):
        from app.sources.huggingface import HuggingFaceSource
        src = HuggingFaceSource(dataset_name="test", max_samples=10)
        assert src is not None


class TestWebsiteSource:
    def test_website_source_instantiates(self):
        from app.sources.website import WebsiteSource
        src = WebsiteSource(urls=["https://example.com"], max_depth=1, max_pages=5)
        assert src is not None


class TestDomainDocument:
    def test_document_defaults(self):
        from app.domain.document import Document
        doc = Document(source="test", source_type=SourceType.API, title="T", text="hello")
        assert doc.language == "en"
        assert doc.id is not None
        assert doc.created_at is not None

    def test_clean_document_defaults(self):
        import uuid
        from app.domain.document import CleanDocument
        doc = CleanDocument(
            source_document_id=uuid.uuid4(),
            source="test",
            source_type=SourceType.API,
            title="T",
            text="hello",
        )
        assert not doc.is_duplicate
        assert doc.quality_score == 1.0
