"""FastAPI dependency injection — services, DB, storage."""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated, AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.rag.embedder import Embedder
from app.rag.vector_store.chroma import make_vector_store
from app.repositories.document import DocumentChunkRepository, DocumentRepository
from app.repositories.job import JobRepository
from app.services.dataset import DatasetService
from app.services.ingestion import IngestionService
from app.services.rag import RAGService
from app.storage.s3 import make_storage_from_settings


# ── Singletons (created once per process) ────────────────────────────────────

@lru_cache(maxsize=1)
def _vector_store():
    return make_vector_store()


@lru_cache(maxsize=1)
def _storage():
    return make_storage_from_settings()


@lru_cache(maxsize=1)
def _embedder():
    return Embedder()


# ── Per-request dependencies ──────────────────────────────────────────────────

def get_vector_store():
    return _vector_store()


def get_storage():
    return _storage()


def get_embedder():
    return _embedder()


def get_document_repo(session: AsyncSession = Depends(get_db)) -> DocumentRepository:
    return DocumentRepository(session)


def get_chunk_repo(session: AsyncSession = Depends(get_db)) -> DocumentChunkRepository:
    return DocumentChunkRepository(session)


def get_job_repo(session: AsyncSession = Depends(get_db)) -> JobRepository:
    return JobRepository(session)


def get_ingestion_service(
    doc_repo: DocumentRepository = Depends(get_document_repo),
    chunk_repo: DocumentChunkRepository = Depends(get_chunk_repo),
) -> IngestionService:
    return IngestionService(
        document_repo=doc_repo,
        chunk_repo=chunk_repo,
        vector_store=_vector_store(),
        storage=_storage(),
        embedder=_embedder(),
    )


def get_rag_service() -> RAGService:
    return RAGService(
        vector_store=_vector_store(),
        storage=_storage(),
        embedder=_embedder(),
    )


def get_dataset_service() -> DatasetService:
    return DatasetService(storage=_storage())
