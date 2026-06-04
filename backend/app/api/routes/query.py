import time

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_rag_engine
from app.db.models import QueryLog
from app.db.session import get_db
from app.models.query import FeedbackRequest, RAGRequest, RAGResponse
from app.services.rag_engine import RAGEngine

router = APIRouter(prefix="/query", tags=["query"])


@router.post("/", response_model=RAGResponse)
async def rag_query(
    payload: RAGRequest,
    engine: RAGEngine = Depends(get_rag_engine),
    db: AsyncSession = Depends(get_db),
):
    response = await engine.answer(
        query=payload.query,
        top_k=payload.top_k,
        filters=payload.filters,
        system_prompt=payload.system_prompt,
    )

    log = QueryLog(
        query_text=payload.query,
        retrieved_doc_ids=[c.document_id for c in response.citations],
        answer=response.answer,
        latency_ms=response.latency_ms,
    )
    db.add(log)
    await db.commit()

    return response


@router.post("/feedback")
async def submit_feedback(payload: FeedbackRequest, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select

    result = await db.execute(select(QueryLog).where(QueryLog.id == payload.query_log_id))
    log = result.scalar_one_or_none()
    if log:
        log.feedback_score = payload.score
        await db.commit()
    return {"status": "ok"}
