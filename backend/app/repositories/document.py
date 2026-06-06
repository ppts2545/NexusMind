from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.db.models.document import Document, DocumentChunk, DocumentStatus
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    model = Document

    async def get_by_hash(self, content_hash: str) -> Document | None:
        result = await self._session.execute(
            select(Document).where(Document.content_hash == content_hash)
        )
        return result.scalar_one_or_none()

    async def get_with_chunks(self, document_id: UUID) -> Document | None:
        from sqlalchemy.orm import selectinload
        result = await self._session.execute(
            select(Document)
            .options(selectinload(Document.chunks))
            .where(Document.id == document_id)
        )
        return result.scalar_one_or_none()

    async def set_status(self, document_id: UUID, status: DocumentStatus, error: str | None = None) -> None:
        doc = await self.get_or_raise(document_id)
        doc.status = status
        if error:
            doc.error_message = error
        await self._session.commit()

    async def list_by_status(self, status: DocumentStatus, limit: int = 100) -> list[Document]:
        result = await self._session.execute(
            select(Document).where(Document.status == status).limit(limit)
        )
        return list(result.scalars().all())


class DocumentChunkRepository(BaseRepository[DocumentChunk]):
    model = DocumentChunk

    async def list_by_document(self, document_id: UUID) -> list[DocumentChunk]:
        result = await self._session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def delete_by_document(self, document_id: UUID) -> int:
        from sqlalchemy import delete
        result = await self._session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        await self._session.commit()
        return result.rowcount
