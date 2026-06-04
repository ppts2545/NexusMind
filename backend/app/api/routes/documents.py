import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.db.models import Document, DocumentSource, DocumentStatus
from app.db.session import get_db
from app.models.document import CrawlRequest, DocumentIngest, DocumentList, DocumentResponse
from app.workers.tasks import crawl_and_ingest, ingest_document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest(payload: DocumentIngest, db: AsyncSession = Depends(get_db)):
    if not payload.content and not payload.source_url:
        raise HTTPException(status_code=400, detail="Provide either 'content' or 'source_url'.")

    doc = Document(
        id=uuid.uuid4(),
        title=payload.title,
        source_url=str(payload.source_url) if payload.source_url else None,
        source_type=DocumentSource.API,
        status=DocumentStatus.PENDING,
        mime_type=payload.mime_type,
        meta=payload.meta,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    content = payload.content or ""
    ingest_document.delay(str(doc.id), content, payload.title, payload.meta)
    return doc


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload(file: UploadFile, db: AsyncSession = Depends(get_db)):
    raw = await file.read()
    try:
        content = raw.decode("utf-8", errors="replace")
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to decode file as text.")

    doc = Document(
        id=uuid.uuid4(),
        title=file.filename or "uploaded_file",
        source_type=DocumentSource.UPLOAD,
        status=DocumentStatus.PENDING,
        mime_type=file.content_type or "text/plain",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    ingest_document.delay(str(doc.id), content, doc.title, None)
    return doc


@router.post("/crawl", status_code=status.HTTP_202_ACCEPTED)
async def crawl(payload: CrawlRequest):
    task = crawl_and_ingest.delay(
        str(payload.url),
        payload.max_depth,
        payload.max_pages,
        payload.follow_external,
    )
    return {"task_id": task.id, "start_url": str(payload.url)}


@router.get("/", response_model=DocumentList)
async def list_documents(page: int = 1, page_size: int = 20, db: AsyncSession = Depends(get_db)):
    offset = (page - 1) * page_size
    total_result = await db.execute(select(func.count()).select_from(Document))
    total = total_result.scalar_one()
    result = await db.execute(select(Document).offset(offset).limit(page_size).order_by(Document.created_at.desc()))
    docs = result.scalars().all()
    return DocumentList(items=list(docs), total=total, page=page, page_size=page_size)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    from app.services.vector_store import VectorStore
    vs = VectorStore()
    await vs.delete_by_document(str(document_id))

    await db.delete(doc)
    await db.commit()
