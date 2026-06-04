import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2048)
    top_k: int = Field(default=5, ge=1, le=50)
    filters: dict | None = None


class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    content: str
    score: float
    rank: int
    meta: dict | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total_retrieved: int
    latency_ms: int


class RAGRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2048)
    top_k: int = Field(default=5, ge=1, le=20)
    filters: dict | None = None
    stream: bool = False
    system_prompt: str | None = None


class Citation(BaseModel):
    document_id: str
    document_title: str
    chunk_content: str
    score: float


class RAGResponse(BaseModel):
    query: str
    answer: str
    citations: list[Citation]
    latency_ms: int
    model: str


class FeedbackRequest(BaseModel):
    query_log_id: uuid.UUID
    score: int = Field(..., ge=1, le=5)
    comment: str | None = None
