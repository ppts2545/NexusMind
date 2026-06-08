"""
Retriever
=========

Retriever คือ "หัวใจ" ของ RAG pipeline
ทำหน้าที่ค้นหา chunks ที่เกี่ยวข้องกับ query ที่สุด

กระบวนการทั้งหมด:
-----------------
1. Intent Classification  → ถาม Claude Haiku ว่า query นี้เกี่ยวกับ topic ไหน
2. Build Filter           → แปลง intent → Qdrant filter dict
3. Embed Query            → แปลง query text → vector (384 มิติ)
4. Vector Search          → ค้นหา top-K chunks ที่ใกล้เคียงที่สุด
5. Rerank                 → เรียงลำดับใหม่ด้วย BM25 + RRF
6. Return results         → ส่งกลับ top-K หลัง rerank

ทำไมต้อง Rerank หลัง Vector Search?
--------------------------------------
Vector search ดีเรื่อง semantic แต่ไม่สนใจ keyword ตรงๆ
BM25 reranker ช่วยให้ผลลัพธ์ที่มี keyword ตรงกับ query
ขึ้นมาอยู่ด้านบนด้วย

ตัวอย่าง:
  Query: "PDPA คืออะไร"
  Vector search อาจได้ chunk เกี่ยวกับ "กฎหมายข้อมูลส่วนตัว" ขึ้นมา
  แต่ BM25 จะดันก้อนที่มีคำว่า "PDPA" ขึ้นมาก่อน

Intent Routing — ทำงานยังไง?
------------------------------
ถ้า use_intent_routing=True:

  Query: "ข่าวการเมืองไทยวันนี้"
    ↓ IntentClassifier
  category: "thai_news", confidence: 0.95
    ↓ build_intent_filter
  filter: {"category": "thai_news", "language": "th"}
    ↓ Qdrant search with filter
  ค้นเฉพาะ chunks ที่มาจาก thai_news sources

Fallback เมื่อไม่พบผลลัพธ์:
------------------------------
ถ้าหลัง filter แล้วไม่เจออะไรเลย (เช่น ยังไม่ได้ crawl thai_news)
→ fallback ค้นทั้ง collection โดยไม่มี filter
→ บอก caller ว่า auto-crawl น่าจะต้องทำ
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.rag.embedder import Embedder
from app.rag.intent_classifier import ClassificationResult, IntentClassifier
from app.rag.reranker import HybridReranker
from app.rag.vector_store.base import VectorSearchResult, VectorStore
from app.rag.vector_store.filters import build_intent_filter

logger = get_logger(__name__)


class Retriever:
    """
    Orchestrates: intent classify → embed → vector search → rerank

    Parameters
    ----------
    vector_store : VectorStore
        Qdrant store (หรือ ChromaDB ถ้าใช้ chroma profile)
    embedder : Embedder | None
        ถ้าไม่ส่งมา → สร้างใหม่โดยอัตโนมัติ
    reranker : HybridReranker | None
        ถ้าไม่ส่งมา → สร้างใหม่โดยอัตโนมัติ
    intent_classifier : IntentClassifier | None
        ถ้าไม่ส่งมา → สร้างใหม่โดยอัตโนมัติ
    """

    def __init__(
        self,
        vector_store: VectorStore,
        embedder: Embedder | None = None,
        reranker: HybridReranker | None = None,
        intent_classifier: IntentClassifier | None = None,
    ) -> None:
        self._store = vector_store
        self._embedder = embedder or Embedder()
        self._reranker = reranker or HybridReranker()
        self._classifier = intent_classifier or IntentClassifier()

    async def retrieve(
        self,
        query: str,
        top_k_retrieve: int = 10,
        top_k_rerank: int = 5,
        filters: dict | None = None,
        use_hybrid: bool = True,
        use_intent_routing: bool = True,
    ) -> tuple[list[VectorSearchResult], float, ClassificationResult | None]:
        """
        ค้นหา chunks ที่เกี่ยวข้องกับ query

        Parameters
        ----------
        query : str
            คำถามหรือ search query จาก user

        top_k_retrieve : int
            จำนวน candidates ที่ดึงจาก Qdrant (ก่อน rerank)
            ควรตั้งไว้สูงกว่า top_k_rerank เพื่อให้ reranker มีตัวเลือกมากขึ้น
            default: 10

        top_k_rerank : int
            จำนวน results สุดท้ายที่ return (หลัง rerank)
            default: 5

        filters : dict | None
            filter เพิ่มเติมที่ caller ต้องการ (merge กับ intent filter อัตโนมัติ)
            เช่น {"source_type": "pdf"} ถ้าอยาก search เฉพาะ PDF

        use_hybrid : bool
            True  → Dense + BM25 hybrid search (แม่นกว่า แต่ต้องมี sparse vectors)
            False → Dense-only search (เร็วกว่า)

        use_intent_routing : bool
            True  → classify query → filter ตาม category (แนะนำ)
            False → ค้นทั้ง collection ไม่มี filter (ใช้ตอน debug หรือ test)

        Returns
        -------
        tuple[list[VectorSearchResult], float, ClassificationResult | None]
          - results   : list ของ chunks ที่ rerank แล้ว
          - best_score: confidence score ของ result อันดับ 1 (ใช้ decide web fallback)
          - intent    : ผลลัพธ์ intent classification (None ถ้าไม่ได้ใช้)
        """
        intent: ClassificationResult | None = None
        effective_filter = filters  # filter เริ่มต้นจาก caller

        # ── Step 1: Intent Classification ────────────────────────────────────
        if use_intent_routing:
            intent = await self._classifier.classify_async(query)

            # สร้าง intent filter จาก category + language
            # เช่น thai_news → {"category": "thai_news", "language": "th"}
            intent_filter = build_intent_filter(
                categories=[intent.category_name],
                language=_guess_language(intent),
            )

            # Merge กับ caller's filter (ถ้ามี)
            # ทั้งสอง filter ต้องผ่านหมด (AND logic)
            if intent_filter and effective_filter:
                effective_filter = {**effective_filter, **intent_filter}
            elif intent_filter:
                effective_filter = intent_filter

            logger.info(
                "intent_routed",
                query=query[:60],
                category=intent.category_name,
                confidence=round(intent.confidence, 2),
                filter=effective_filter,
            )

        # ── Step 2: Embed Query ───────────────────────────────────────────────
        # แปลง query string → vector ขนาด 384 มิติ
        # ต้องใช้ model เดียวกับตอน index ข้อมูล
        embedding = await self._embedder.embed_one_async(query)

        # ── Step 3: Vector Search ─────────────────────────────────────────────
        if use_hybrid:
            raw_results = await self._store.hybrid_query(
                embedding=embedding,
                text=query,
                top_k=top_k_retrieve,
                filters=effective_filter,
            )
        else:
            raw_results = await self._store.query(
                embedding=embedding,
                top_k=top_k_retrieve,
                filters=effective_filter,
            )

        # ── Step 4: Fallback เมื่อไม่พบผลลัพธ์ ─────────────────────────────
        # กรณี: filter ตาม category แต่ยังไม่ได้ crawl source นั้นเลย
        # → ลอง search โดยไม่มี filter เพื่อดูว่ามีข้อมูลที่เกี่ยวข้องบ้างไหม
        if not raw_results and effective_filter is not None:
            logger.info(
                "retriever_filter_no_results_fallback",
                category=intent.category_name if intent else "n/a",
            )
            raw_results = await self._store.query(
                embedding=embedding,
                top_k=top_k_retrieve,
                filters=None,  # ไม่มี filter = ค้นทั้งหมด
            )

        if not raw_results:
            return [], 0.0, intent

        # ── Step 5: Rerank ────────────────────────────────────────────────────
        # เรียงลำดับใหม่ด้วย BM25 + Reciprocal Rank Fusion
        # ผลคือ chunks ที่มีทั้ง semantic AND keyword match จะขึ้นมาก่อน
        reranked = self._reranker.rerank(query, raw_results, top_k=top_k_rerank)
        best_score = reranked[0].score if reranked else 0.0

        logger.info(
            "retriever_done",
            retrieved=len(raw_results),
            reranked=len(reranked),
            best_score=round(best_score, 3),
        )
        return reranked, best_score, intent


# ── Helpers ──────────────────────────────────────────────────────────────────

def _guess_language(intent: ClassificationResult) -> str | None:
    """
    เดาภาษาที่ควร filter จาก category

    ตัวอย่าง:
      thai_news     → "th"  (ข่าวไทยควรเป็นภาษาไทย)
      academic_ai   → None  (AI research มีทั้ง EN และ TH)
      tech_docs     → "en"  (เอกสาร tech ส่วนใหญ่เป็น English)
      general       → None  (ไม่ระบุภาษา)

    ทำไมไม่ filter language ทุก category?
      เพราะ category บางอย่างมีทั้งสองภาษา เช่น academic_ai
      ถ้า filter language="th" อาจพลาด paper ภาษา EN ที่เกี่ยวข้อง
    """
    LANGUAGE_BY_CATEGORY: dict[str, str] = {
        "thai_news":       "th",
        "thai_finance":    "th",
        "thai_law":        "th",
        "thai_government": "th",
        "tech_docs":       "en",
        # academic_ai  → ไม่ระบุ (มีทั้ง TH และ EN)
        # general      → ไม่ระบุ
    }
    return LANGUAGE_BY_CATEGORY.get(intent.category_name)
