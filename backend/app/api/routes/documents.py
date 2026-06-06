"""Document management endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.api.deps import get_document_repo, get_ingestion_service, get_vector_store
from app.repositories.document import DocumentRepository
from app.services.ingestion import IngestionService

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentIngestRequest(BaseModel):
    title: str
    content: str | None = None
    url: str | None = None
    source: str = "api"
    meta: dict | None = None


class DocumentResponse(BaseModel):
    id: str
    title: str
    source: str
    source_type: str
    url: str | None
    status: str
    chunk_count: int
    word_count: int
    language: str | None
    created_at: str

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_document(
    payload: DocumentIngestRequest,
    ingestion: IngestionService = Depends(get_ingestion_service),
    doc_repo: DocumentRepository = Depends(get_document_repo),
):
    if not payload.content and not payload.url:
        raise HTTPException(status_code=400, detail="Provide 'content' or 'url'.")

    content = payload.content or ""
    await ingestion.ingest_text(payload.title, content, source=payload.source, url=payload.url)

    docs = await doc_repo.list(limit=1)
    if not docs:
        raise HTTPException(status_code=500, detail="Ingestion failed silently.")

    return _doc_response(docs[0])


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile,
    ingestion: IngestionService = Depends(get_ingestion_service),
    doc_repo: DocumentRepository = Depends(get_document_repo),
):
    raw = await file.read()
    content = raw.decode("utf-8", errors="replace")

    await ingestion.ingest_text(
        title=file.filename or "uploaded_file",
        text=content,
        source=f"upload:{file.filename}",
    )

    docs = await doc_repo.list(limit=1)
    if not docs:
        raise HTTPException(status_code=500, detail="Upload ingestion failed.")
    return _doc_response(docs[0])


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    doc_repo: DocumentRepository = Depends(get_document_repo),
):
    offset = (page - 1) * page_size
    items = await doc_repo.list(offset=offset, limit=page_size)
    total = await doc_repo.count()
    return DocumentListResponse(
        items=[_doc_response(d) for d in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    doc_repo: DocumentRepository = Depends(get_document_repo),
):
    doc = await doc_repo.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return _doc_response(doc)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    doc_repo: DocumentRepository = Depends(get_document_repo),
    vector_store=Depends(get_vector_store),
):
    doc = await doc_repo.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    await vector_store.delete_by_document(str(document_id))
    await doc_repo.delete(doc)


def _doc_response(d) -> DocumentResponse:
    return DocumentResponse(
        id=str(d.id),
        title=d.title,
        source=d.source,
        source_type=str(d.source_type),
        url=d.url,
        status=str(d.status),
        chunk_count=d.chunk_count,
        word_count=getattr(d, "word_count", 0),
        language=d.language,
        created_at=d.created_at.isoformat(),
    )
