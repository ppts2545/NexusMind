import uuid
from dataclasses import dataclass, field

import chromadb
from chromadb import AsyncHttpClient

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class VectorMatch:
    id: str
    score: float
    content: str
    meta: dict = field(default_factory=dict)


class VectorStore:
    def __init__(self) -> None:
        self._client: AsyncHttpClient | None = None
        self._collection = None

    async def _get_collection(self):
        if self._collection is None:
            self._client = await chromadb.AsyncHttpClient(
                host=settings.CHROMA_HOST,
                port=settings.CHROMA_PORT,
            )
            self._collection = await self._client.get_or_create_collection(
                name=settings.CHROMA_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    async def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        collection = await self._get_collection()
        await collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        logger.info("vectors_upserted", count=len(ids))

    async def query(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        where: dict | None = None,
    ) -> list[VectorMatch]:
        collection = await self._get_collection()
        result = await collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        matches: list[VectorMatch] = []
        for i, doc_id in enumerate(result["ids"][0]):
            matches.append(
                VectorMatch(
                    id=doc_id,
                    score=1.0 - result["distances"][0][i],  # cosine distance → similarity
                    content=result["documents"][0][i],
                    meta=result["metadatas"][0][i] or {},
                )
            )
        return matches

    async def delete_by_document(self, document_id: str) -> None:
        collection = await self._get_collection()
        await collection.delete(where={"document_id": document_id})
        logger.info("vectors_deleted", document_id=document_id)
