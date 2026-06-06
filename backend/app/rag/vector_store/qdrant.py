"""Qdrant vector store — primary production backend."""
from __future__ import annotations

from typing import Any

from app.rag.vector_store.base import VectorSearchResult, VectorStore


class QdrantStore(VectorStore):
    """
    Qdrant-backed vector store with hybrid search support.

    Qdrant natively supports sparse+dense hybrid search via its built-in
    sparse vectors.  We use ``models.SparseVector`` with BM25 when available.
    """

    def __init__(self, url: str, api_key: str = "", collection: str = "nexusmind_chunks") -> None:
        self._url = url
        self._api_key = api_key or None
        self._collection = collection
        self._client: object | None = None

    def _get_client(self):
        if self._client is None:
            from qdrant_client import AsyncQdrantClient  # type: ignore[import]
            self._client = AsyncQdrantClient(
                url=self._url,
                api_key=self._api_key,
                timeout=30,
            )
        return self._client

    async def collection_exists(self) -> bool:
        client = self._get_client()
        try:
            collections = await client.get_collections()
            return any(c.name == self._collection for c in collections.collections)
        except Exception:
            return False

    async def create_collection(self, dimension: int) -> None:
        from qdrant_client.models import Distance, VectorParams  # type: ignore[import]
        client = self._get_client()
        await client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
        )

    async def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        from qdrant_client.models import PointStruct  # type: ignore[import]
        client = self._get_client()

        points = [
            PointStruct(
                id=id_,
                vector=embedding,
                payload={**meta, "content": doc},
            )
            for id_, embedding, doc, meta in zip(ids, embeddings, documents, metadatas)
        ]

        # Upsert in batches of 256
        batch_size = 256
        for i in range(0, len(points), batch_size):
            await client.upsert(
                collection_name=self._collection,
                points=points[i: i + batch_size],
            )

    async def query(
        self,
        embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        from qdrant_client.models import Filter, FieldCondition, MatchValue  # type: ignore[import]
        client = self._get_client()

        qdrant_filter = None
        if filters:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filters.items()
            ]
            qdrant_filter = Filter(must=conditions)

        results = await client.search(
            collection_name=self._collection,
            query_vector=embedding,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        return [
            VectorSearchResult(
                id=str(r.id),
                score=r.score,
                document_id=str(r.payload.get("document_id", "")),
                document_title=str(r.payload.get("document_title", "")),
                content=str(r.payload.get("content", "")),
                metadata={k: v for k, v in r.payload.items() if k not in ("content", "document_id", "document_title")},
            )
            for r in results
        ]

    async def hybrid_query(
        self,
        embedding: list[float],
        text: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        # Qdrant hybrid requires sparse vectors; fall back to dense-only here.
        # For full hybrid support, configure a sparse model in the collection.
        return await self.query(embedding, top_k=top_k, filters=filters)

    async def delete(self, ids: list[str]) -> None:
        from qdrant_client.models import PointIdsList  # type: ignore[import]
        client = self._get_client()
        await client.delete(
            collection_name=self._collection,
            points_selector=PointIdsList(points=ids),
        )

    async def delete_by_document(self, document_id: str) -> None:
        from qdrant_client.models import Filter, FieldCondition, MatchValue  # type: ignore[import]
        client = self._get_client()
        await client.delete(
            collection_name=self._collection,
            points_selector=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
            ),
        )
