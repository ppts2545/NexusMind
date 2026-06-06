"""ChromaDB vector store — backward-compatible fallback."""
from __future__ import annotations

from typing import Any

from app.rag.vector_store.base import VectorSearchResult, VectorStore


class ChromaStore(VectorStore):
    """Wraps ChromaDB async HTTP client for backward compatibility."""

    def __init__(self, host: str = "localhost", port: int = 8001, collection: str = "nexusmind_docs") -> None:
        self._host = host
        self._port = port
        self._collection_name = collection
        self._client: object | None = None
        self._collection: object | None = None

    def _get_client(self):
        if self._client is None:
            import chromadb  # type: ignore[import]
            self._client = chromadb.AsyncHttpClient(host=self._host, port=self._port)
        return self._client

    async def _get_collection(self):
        if self._collection is None:
            client = self._get_client()
            self._collection = await client.get_or_create_collection(self._collection_name)
        return self._collection

    async def collection_exists(self) -> bool:
        try:
            client = self._get_client()
            cols = await client.list_collections()
            return any(c.name == self._collection_name for c in cols)
        except Exception:
            return False

    async def create_collection(self, dimension: int) -> None:
        await self._get_collection()

    async def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        col = await self._get_collection()
        batch_size = 512
        for i in range(0, len(ids), batch_size):
            await col.upsert(
                ids=ids[i: i + batch_size],
                embeddings=embeddings[i: i + batch_size],
                documents=documents[i: i + batch_size],
                metadatas=metadatas[i: i + batch_size],
            )

    async def query(
        self,
        embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        col = await self._get_collection()
        where = filters if filters else None
        results = await col.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        output: list[VectorSearchResult] = []
        for i, (doc_id, doc, meta, dist) in enumerate(
            zip(
                results["ids"][0],
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ):
            output.append(
                VectorSearchResult(
                    id=doc_id,
                    score=1 - dist,
                    document_id=str(meta.get("document_id", "")),
                    document_title=str(meta.get("document_title", "")),
                    content=doc,
                    metadata=meta,
                )
            )
        return output

    async def hybrid_query(
        self,
        embedding: list[float],
        text: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        return await self.query(embedding, top_k=top_k, filters=filters)

    async def delete(self, ids: list[str]) -> None:
        col = await self._get_collection()
        await col.delete(ids=ids)

    async def delete_by_document(self, document_id: str) -> None:
        col = await self._get_collection()
        await col.delete(where={"document_id": document_id})


def make_vector_store() -> VectorStore:
    """Factory — reads settings and returns the configured VectorStore."""
    from app.core.config import get_settings
    settings = get_settings()

    if settings.VECTOR_STORE == "qdrant":
        from app.rag.vector_store.qdrant import QdrantStore
        return QdrantStore(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            collection=settings.QDRANT_COLLECTION,
        )

    from app.rag.vector_store.chroma import ChromaStore
    return ChromaStore(
        host=settings.CHROMA_HOST,
        port=settings.CHROMA_PORT,
        collection=settings.CHROMA_COLLECTION,
    )
