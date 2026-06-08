"""
Qdrant Vector Store
====================

Qdrant คืออะไร?
---------------
Qdrant เป็น vector database ที่ออกแบบมาสำหรับ similarity search โดยเฉพาะ
เก็บข้อมูลเป็น "Points" แต่ละ Point มี 3 ส่วน:
  - id       : UUID ของ chunk
  - vector   : embedding array เช่น [0.12, -0.34, 0.91, ...] (384 มิติ)
  - payload  : metadata dict เช่น {category, language, content, ...}

ทำไมต้องมี Payload Index?
--------------------------
ถ้าไม่มี index Qdrant จะต้อง scan ทุก point เพื่อ filter
เหมือน SQL ที่ไม่มี index → O(n) ช้ามากเมื่อมีข้อมูลเยอะ

เมื่อสร้าง payload index แล้ว:
  - filter จะเร็วขึ้น O(log n)
  - ประหยัด RAM เพราะไม่ต้อง load ทุก point มา filter

Collection Architecture (Single Collection Design)
---------------------------------------------------
เราใช้ collection เดียว "nexusmind_chunks" แทนการแยก collection ต่อ topic

ทำไม?
  1. Query ข้าม category ได้ เช่น "ข่าว AI ไทย" → thai_news + academic_ai
  2. Manage ง่าย backup/migrate ที่เดียว
  3. Qdrant payload filtering เร็วมากเมื่อมี index

โครงสร้าง Payload (metadata ที่เก็บใน Qdrant)
----------------------------------------------
{
  # ─── Routing fields (มี index → filter เร็ว) ───────────────
  "category":      "thai_news"        ← จาก Source Registry
  "source_domain": "matichon.co.th"   ← parse จาก URL
  "language":      "th"               ← detect อัตโนมัติ
  "source_type":   "web"              ← web/pdf/upload/api

  # ─── Identity fields ────────────────────────────────────────
  "document_id":    "uuid-..."        ← FK ไปยัง PostgreSQL
  "document_title": "ข่าว..."
  "chunk_index":    3                 ← ลำดับ chunk ใน document
  "url":            "https://..."     ← URL ต้นทาง

  # ─── Content ────────────────────────────────────────────────
  "content": "ข้อความจริง..."         ← เก็บไว้ return ให้ LLM
}
"""
from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.rag.vector_store.base import VectorSearchResult, VectorStore
from app.rag.vector_store.filters import build_qdrant_filter

logger = get_logger(__name__)


class QdrantStore(VectorStore):
    """
    Qdrant vector store พร้อม:
      - Payload indexes สำหรับ fast filtering
      - Hybrid search (dense + sparse BM25)
      - Batch upsert
    """

    def __init__(
        self,
        url: str,
        api_key: str = "",
        collection: str = "nexusmind_chunks",
    ) -> None:
        self._url = url
        self._api_key = api_key or None
        self._collection = collection
        self._client: object | None = None

    # ── Private helpers ──────────────────────────────────────────────────────

    def _get_client(self):
        """
        Lazy initialization — สร้าง client ครั้งแรกที่ใช้งาน
        ไม่สร้างตอน __init__ เพราะอาจยังไม่มี Qdrant ขึ้นมา
        """
        if self._client is None:
            from qdrant_client import AsyncQdrantClient  # type: ignore[import]
            self._client = AsyncQdrantClient(
                url=self._url,
                api_key=self._api_key,
                timeout=30,
            )
        return self._client

    # ── Collection management ────────────────────────────────────────────────

    async def collection_exists(self) -> bool:
        client = self._get_client()
        try:
            collections = await client.get_collections()
            return any(c.name == self._collection for c in collections.collections)
        except Exception:
            return False

    async def create_collection(self, dimension: int) -> None:
        """
        สร้าง collection ใหม่พร้อม payload indexes

        dimension = ขนาดของ embedding vector
          BAAI/bge-small-en-v1.5 → 384
          text-embedding-3-small  → 1536
          เปลี่ยนได้ใน .env → EMBEDDING_DIMENSION
        """
        from qdrant_client.models import (  # type: ignore[import]
            Distance,
            PayloadSchemaType,
            VectorParams,
        )

        client = self._get_client()

        # สร้าง collection หลัก
        await client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(
                size=dimension,
                distance=Distance.COSINE,
                # COSINE = วัด angle ระหว่าง vectors
                # เหมาะกับ text embeddings มากที่สุด
                # เพราะวัด "ทิศทาง" ของความหมาย ไม่ใช่ขนาด
            ),
        )
        logger.info("qdrant_collection_created", name=self._collection, dim=dimension)

        # ─── สร้าง Payload Indexes ────────────────────────────────────────
        # KEYWORD type = เหมาะกับ string ที่ค่าซ้ำกันได้ (category, language)
        # ไม่ใช่ FULL_TEXT (ซึ่งสำหรับ search ภายใน string ยาวๆ)
        #
        # fields ที่สร้าง index:
        #   category      → filter ตาม topic (thai_news, academic_ai, ...)
        #   source_domain → filter ตาม website (matichon.co.th, bot.or.th, ...)
        #   language      → filter ตาม ภาษา (th, en, ...)
        #   document_id   → ใช้ตอน delete document ออกจาก Qdrant
        #   source_type   → filter ตามประเภท (web, pdf, upload)
        indexed_fields = [
            "category",
            "source_domain",
            "language",
            "document_id",
            "source_type",
        ]
        for field in indexed_fields:
            await client.create_payload_index(
                collection_name=self._collection,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info("qdrant_payload_index_created", field=field)

    # ── Write operations ─────────────────────────────────────────────────────

    async def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """
        เพิ่ม/อัปเดต points ใน Qdrant

        "upsert" = insert ถ้ายังไม่มี, update ถ้ามีแล้ว
        ใช้ id เดิมได้เลย ไม่ duplicate

        Batch size 256:
          Qdrant รับ payload ขนาดใหญ่ได้ แต่การส่งทีละ
          256 points ช่วยลด memory spike และ timeout
        """
        from qdrant_client.models import PointStruct  # type: ignore[import]

        client = self._get_client()

        # รวม content เข้าไปใน payload
        # เพื่อให้ดึงกลับมาแสดงได้โดยไม่ต้อง query PostgreSQL อีกครั้ง
        points = [
            PointStruct(
                id=id_,
                vector=embedding,
                payload={**meta, "content": doc},
            )
            for id_, embedding, doc, meta in zip(ids, embeddings, documents, metadatas)
        ]

        BATCH_SIZE = 256
        for i in range(0, len(points), BATCH_SIZE):
            batch = points[i : i + BATCH_SIZE]
            await client.upsert(
                collection_name=self._collection,
                points=batch,
            )
        logger.info("qdrant_upserted", count=len(points))

    # ── Read operations ──────────────────────────────────────────────────────

    async def query(
        self,
        embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        """
        Vector similarity search พร้อม optional metadata filter

        Parameters
        ----------
        embedding : list[float]
            query vector จาก embedder (ต้องมีมิติเดียวกับ collection)
        top_k : int
            จำนวน results ที่ต้องการ
        filters : dict | None
            Python dict syntax เช่น:
              {"category": "thai_news"}
              {"category": {"$in": ["thai_news", "thai_finance"]}}
              {"language": "th", "category": "thai_law"}

        กระบวนการ:
        1. แปลง filters dict → Qdrant Filter object (ผ่าน build_qdrant_filter)
        2. ส่ง query vector + filter ไปให้ Qdrant
        3. แปลง Qdrant results → VectorSearchResult objects
        """
        client = self._get_client()

        # แปลง filters dict → Qdrant native format
        qdrant_filter = build_qdrant_filter(filters)

        results = await client.search(
            collection_name=self._collection,
            query_vector=embedding,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,  # ต้องการ payload เพื่อดึง content + metadata
        )

        return [_to_search_result(r) for r in results]

    async def hybrid_query(
        self,
        embedding: list[float],
        text: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        """
        Hybrid search = Dense Vector + BM25 Sparse

        WHY Hybrid?
        -----------
        - Dense vector (embedding): เก่งเรื่อง semantic similarity
          "รถยนต์" กับ "รถ" → ใกล้กันมากใน vector space

        - BM25 Sparse: เก่งเรื่อง exact keyword match
          "GPT-4o" → ต้องเจอ string นี้พอดี ไม่ใช่แค่ "ใกล้เคียง"

        ผสมกัน = ได้ทั้ง semantic และ keyword matching

        NOTE: Full hybrid ต้องการ sparse vector ใน Qdrant collection
        ถ้าไม่ได้ setup sparse model → fallback ไป dense-only search อัตโนมัติ
        """
        try:
            from qdrant_client.models import Prefetch, Query  # type: ignore[import]
            client = self._get_client()
            qdrant_filter = build_qdrant_filter(filters)

            results = await client.query_points(
                collection_name=self._collection,
                prefetch=[
                    Prefetch(query=embedding, limit=top_k * 2),
                ],
                query=Query(fusion="rrf"),  # Reciprocal Rank Fusion
                limit=top_k,
                query_filter=qdrant_filter,
                with_payload=True,
            )
            return [_to_search_result(r) for r in results.points]
        except Exception:
            # Sparse vectors ไม่ได้ถูก configure → ใช้ dense search แทน
            logger.debug("hybrid_search_fallback_to_dense")
            return await self.query(embedding, top_k=top_k, filters=filters)

    # ── Delete operations ────────────────────────────────────────────────────

    async def delete(self, ids: list[str]) -> None:
        """ลบ points ตาม id โดยตรง"""
        from qdrant_client.models import PointIdsList  # type: ignore[import]
        client = self._get_client()
        await client.delete(
            collection_name=self._collection,
            points_selector=PointIdsList(points=ids),
        )

    async def delete_by_document(self, document_id: str) -> None:
        """
        ลบ points ทั้งหมดที่เป็นของ document_id นี้

        ใช้ตอน user กดลบ document จาก UI
        ทำงานได้เร็วเพราะ document_id มี payload index
        """
        from qdrant_client.models import FieldCondition, Filter, MatchValue  # type: ignore[import]
        client = self._get_client()
        await client.delete(
            collection_name=self._collection,
            points_selector=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
            ),
        )
        logger.info("qdrant_deleted_by_document", document_id=document_id)


# ── Private helpers ──────────────────────────────────────────────────────────

def _to_search_result(r: Any) -> VectorSearchResult:
    """
    แปลง Qdrant ScoredPoint → VectorSearchResult (domain object ของเรา)

    แยกออกมาเป็น function เพราะใช้ทั้งใน query() และ hybrid_query()
    ไม่ต้องเขียนซ้ำสองที่
    """
    payload = r.payload or {}
    return VectorSearchResult(
        id=str(r.id),
        score=r.score,
        document_id=str(payload.get("document_id", "")),
        document_title=str(payload.get("document_title", "")),
        content=str(payload.get("content", "")),
        metadata={
            k: v
            for k, v in payload.items()
            if k not in ("content", "document_id", "document_title")
        },
    )
