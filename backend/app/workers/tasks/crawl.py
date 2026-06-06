"""Crawl + ingest background task."""
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


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30, name="nexusmind.crawl_and_ingest")
def crawl_and_ingest(
    self,
    job_id: str,
    urls: list[str],
    max_depth: int = 2,
    max_pages: int = 50,
    follow_external: bool = False,
) -> dict[str, Any]:
    async def _run_async():
        from app.db.session import AsyncSessionLocal
        from app.repositories.document import DocumentChunkRepository, DocumentRepository
        from app.repositories.job import JobRepository
        from app.db.models.job import JobStatus
        from app.rag.vector_store.chroma import make_vector_store
        from app.services.ingestion import IngestionService
        from app.sources.website import WebsiteSource
        from app.storage.s3 import make_storage_from_settings

        async with AsyncSessionLocal() as session:
            job_repo = JobRepository(session)
            doc_repo = DocumentRepository(session)
            chunk_repo = DocumentChunkRepository(session)

            await job_repo.mark_started(uuid.UUID(job_id), self.request.id)

            try:
                source = WebsiteSource(
                    urls=urls,
                    max_depth=max_depth,
                    max_pages=max_pages,
                    follow_external=follow_external,
                )
                vector_store = make_vector_store()
                storage = make_storage_from_settings()
                service = IngestionService(doc_repo, chunk_repo, vector_store, storage)

                result = await service.ingest_source(source, job_id=job_id)

                await job_repo.mark_success(uuid.UUID(job_id), result, result.get("indexed", 0))
                return result

            except Exception as exc:
                await job_repo.mark_failed(uuid.UUID(job_id), str(exc))
                raise self.retry(exc=exc)

    try:
        return _run(_run_async())
    except Exception as exc:
        raise self.retry(exc=exc)
