from fastapi import APIRouter, Depends

from app.api.dependencies import get_rag_engine
from app.models.query import FeedbackRequest, SearchRequest, SearchResponse
from app.services.rag_engine import RAGEngine

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/", response_model=SearchResponse)
async def search(payload: SearchRequest, engine: RAGEngine = Depends(get_rag_engine)):
    results, latency_ms = await engine.search(
        query=payload.query,
        top_k=payload.top_k,
        filters=payload.filters,
    )
    return SearchResponse(
        query=payload.query,
        results=results,
        total_retrieved=len(results),
        latency_ms=latency_ms,
    )
