"""Embed + index a pre-stored document."""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.workers.celery_app import celery_app


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30, name="nexusmind.embed_document")
def embed_document(
    self,
    document_id: str,
    content: str,
    title: str,
    meta: dict | None = None,
) -> dict[str, Any]:
    async def _run_async():
        from app.db.models.document import DocumentStatus
        from app.db.models.document import DocumentChunk as DBChunk
        from app.db.session import AsyncSessionLocal
        from app.domain.document import CleanDocument, SourceType
        from app.rag.chunker import RecursiveChunker
        from app.rag.embedder import Embedder
        from app.rag.vector_store.chroma import make_vector_store
        from app.repositories.document import DocumentRepository
        from app.core.config import get_settings

        settings = get_settings()
        embedder = Embedder()
        vector_store = make_vector_store()
        chunker = RecursiveChunker(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )

        async with AsyncSessionLocal() as session:
            doc_repo = DocumentRepository(session)
            doc_uuid = uuid.UUID(document_id)

            await doc_repo.set_status(doc_uuid, DocumentStatus.PROCESSING)

            clean = CleanDocument(
                source_document_id=doc_uuid,
                source=meta.get("source_url", "api") if meta else "api",
                source_type=SourceType.API,
                title=title,
                text=content,
                word_count=len(content.split()),
            )

            chunks = chunker.chunk(clean)
            texts = [c.content for c in chunks]
            embeddings = await embedder.embed_async(texts)

            vector_ids = [str(uuid.uuid4()) for _ in chunks]
            metadatas = [
                {
                    "document_id": document_id,
                    "document_title": title,
                    "chunk_index": c.chunk_index,
                }
                for c in chunks
            ]

            await vector_store.upsert(
                ids=vector_ids, embeddings=embeddings, documents=texts, metadatas=metadatas
            )

            db_doc = await doc_repo.get_or_raise(doc_uuid)
            for c, vid in zip(chunks, vector_ids):
                session.add(DBChunk(
                    document_id=doc_uuid,
                    chunk_index=c.chunk_index,
                    content=c.content,
                    token_count=c.token_count,
                    vector_id=vid,
                    meta=c.metadata,
                ))

            await doc_repo.update(db_doc, status=DocumentStatus.INDEXED, chunk_count=len(chunks))

            return {"document_id": document_id, "chunks": len(chunks), "status": "indexed"}

    try:
        return _run(_run_async())
    except Exception as exc:
        raise self.retry(exc=exc)
