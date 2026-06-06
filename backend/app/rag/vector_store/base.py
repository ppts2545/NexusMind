"""VectorStore abstraction — pluggable vector database backend."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorSearchResult:
    id: str
    score: float
    document_id: str
    document_title: str
    content: str
    metadata: dict = field(default_factory=dict)


class VectorStore(ABC):
    """
    Pluggable vector store interface.

    Implementations: QdrantStore, ChromaStore.
    Swap by changing VECTOR_STORE env var — no service code changes required.
    """

    @abstractmethod
    async def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Insert or update vectors with their content and metadata."""

    @abstractmethod
    async def query(
        self,
        embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        """Dense vector similarity search."""

    @abstractmethod
    async def hybrid_query(
        self,
        embedding: list[float],
        text: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        """
        Hybrid search combining dense vectors + sparse BM25.

        Falls back to dense-only if the backend doesn't support hybrid.
        """

    @abstractmethod
    async def delete(self, ids: list[str]) -> None:
        """Delete vectors by their IDs."""

    @abstractmethod
    async def delete_by_document(self, document_id: str) -> None:
        """Delete all vectors belonging to a document."""

    @abstractmethod
    async def collection_exists(self) -> bool:
        """Return True if the collection/index has been created."""

    @abstractmethod
    async def create_collection(self, dimension: int) -> None:
        """Create the collection/index if it doesn't exist."""
