"""
Canonical domain models — the universal format every data source normalizes to.

All pipelines (RAG, fine-tuning, pre-training) operate on these types.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    WEB = "web"
    PDF = "pdf"
    DATABASE = "database"
    HUGGINGFACE = "huggingface"
    COMMON_CRAWL = "common_crawl"
    UPLOAD = "upload"
    API = "api"


class Document(BaseModel):
    """Universal document format. Every source adapter must produce this."""

    id: UUID = Field(default_factory=uuid4)
    source: str                          # human-readable origin: URL, file path, dataset name
    source_type: SourceType
    url: str | None = None               # canonical URL if applicable
    title: str
    text: str
    language: str = "en"
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CleanDocument(BaseModel):
    """Document after passing through the cleaning pipeline."""

    id: UUID = Field(default_factory=uuid4)
    source_document_id: UUID
    source: str
    source_type: SourceType
    url: str | None = None
    title: str
    text: str                            # cleaned, normalized text
    language: str = "en"
    word_count: int = 0
    quality_score: float = 1.0           # 0.0–1.0
    is_duplicate: bool = False
    minhash_signature: list[int] | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TextChunk(BaseModel):
    """A single chunk produced by the chunker."""

    id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    chunk_index: int
    content: str
    token_count: int = 0
    metadata: dict = Field(default_factory=dict)  # inherits source + position info
