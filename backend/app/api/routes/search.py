"""Search + RAG query endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_rag_service
from app.services.rag import RAGService

router = APIRouter(tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2048)
    top_k: int = Field(default=5, ge=1, le=50)
    filters: dict | None = None


class SearchResultItem(BaseModel):
    id: str
    score: float
    document_id: str
    document_title: str
    content: str
    metadata: dict


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
    latency_ms: int
    confidence: float


class RAGRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2048)
    top_k: int = Field(default=5, ge=1, le=20)
    filters: dict | None = None
    system_prompt: str | None = None


class CitationItem(BaseModel):
    index: int
    document_id: str
    document_title: str
    chunk_content: str
    score: float
    url: str | None = None


class RAGResponse(BaseModel):
    query: str
    answer: str
    citations: list[CitationItem]
    latency_ms: int
    model: str
    used_web_fallback: bool
    confidence: float


@router.post("/search", response_model=SearchResponse)
async def search(
    payload: SearchRequest,
    rag: RAGService = Depends(get_rag_service),
):
    result = await rag.search(payload.query, top_k=payload.top_k, filters=payload.filters)
    return SearchResponse(
        query=result.query,
        results=[
            SearchResultItem(
                id=r.id,
                score=r.score,
                document_id=r.document_id,
                document_title=r.document_title,
                content=r.content,
                metadata=r.metadata,
            )
            for r in result.results
        ],
        latency_ms=result.latency_ms,
        confidence=result.confidence,
    )


@router.post("/query", response_model=RAGResponse)
async def query(
    payload: RAGRequest,
    rag: RAGService = Depends(get_rag_service),
):
    result = await rag.answer(
        payload.query,
        top_k=payload.top_k,
        filters=payload.filters,
        system_prompt=payload.system_prompt,
    )
    return RAGResponse(
        query=result.query,
        answer=result.answer,
        citations=[CitationItem(**c) for c in result.citations],
        latency_ms=result.latency_ms,
        model=result.model,
        used_web_fallback=result.used_web_fallback,
        confidence=result.confidence,
    )
