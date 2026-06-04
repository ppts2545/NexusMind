import asyncio
import uuid
from typing import Any

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "nexusmind",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def ingest_document(self, document_id: str, content: str, title: str, meta: dict | None = None) -> dict[str, Any]:
    from app.db.models import DocumentStatus
    from app.db.session import AsyncSessionLocal
    from app.services.embedder import Embedder
    from app.services.processor import DocumentProcessor
    from app.services.vector_store import VectorStore
    from sqlalchemy import select
    from app.db.models import Document, DocumentChunk

    async def _ingest():
        processor = DocumentProcessor()
        embedder = Embedder()
        vector_store = VectorStore()

        cleaned, chunks, language, content_hash = processor.process(content, meta)

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
            doc = result.scalar_one_or_none()
            if doc is None:
                raise ValueError(f"Document {document_id} not found")

            doc.status = DocumentStatus.PROCESSING
            doc.language = language
            doc.content_hash = content_hash
            await db.commit()

            texts = [c.content for c in chunks]
            embeddings = embedder.embed(texts)

            vector_ids: list[str] = []
            db_chunks: list[DocumentChunk] = []
            for chunk, embedding in zip(chunks, embeddings):
                vid = str(uuid.uuid4())
                vector_ids.append(vid)
                db_chunks.append(
                    DocumentChunk(
                        document_id=doc.id,
                        chunk_index=chunk.index,
                        content=chunk.content,
                        token_count=chunk.token_count,
                        vector_id=vid,
                        meta=chunk.meta,
                    )
                )

            await vector_store.upsert(
                ids=vector_ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=[
                    {"document_id": document_id, "document_title": title, "chunk_index": c.index}
                    for c in chunks
                ],
            )

            db.add_all(db_chunks)
            doc.chunk_count = len(chunks)
            doc.status = DocumentStatus.INDEXED
            await db.commit()

        return {"document_id": document_id, "chunks": len(chunks), "status": "indexed"}

    try:
        return _run_async(_ingest())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2)
def crawl_and_ingest(self, start_url: str, max_depth: int, max_pages: int, follow_external: bool) -> dict[str, Any]:
    from app.services.crawler import WebCrawler

    async def _crawl():
        crawler = WebCrawler()
        pages = await crawler.crawl(start_url, max_depth=max_depth, max_pages=max_pages, follow_external=follow_external)
        queued: list[str] = []
        for page in pages:
            doc_id = str(uuid.uuid4())
            ingest_document.delay(doc_id, page.content, page.title, {"source_url": page.url})
            queued.append(doc_id)
        return {"queued": len(queued), "start_url": start_url}

    try:
        return _run_async(_crawl())
    except Exception as exc:
        raise self.retry(exc=exc)
