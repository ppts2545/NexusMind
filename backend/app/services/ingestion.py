"""Ingestion service — orchestrates source → clean → storage → embed."""
from __future__ import annotations

import uuid
from typing import AsyncIterator

from app.cleaning.cleaner import TextCleaner
from app.cleaning.deduplicator import MinHashDeduplicator
from app.cleaning.filters import CleaningPipeline
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models.document import DocumentSource, DocumentStatus
from app.domain.document import CleanDocument, Document, SourceType
from app.rag.chunker import RecursiveChunker
from app.rag.embedder import Embedder
from app.rag.vector_store.base import VectorStore
from app.repositories.document import DocumentChunkRepository, DocumentRepository
from app.sources.base import BaseSource
from app.storage.base import ObjectStorage

logger = get_logger(__name__)


class IngestionService:
    """
    End-to-end ingestion:
        source.load() → clean → dedup → filter → object_storage → embed → vector_db → postgres
    """

    def __init__(
        self,
        document_repo: DocumentRepository,
        chunk_repo: DocumentChunkRepository,
        vector_store: VectorStore,
        storage: ObjectStorage,
        embedder: Embedder | None = None,
    ) -> None:
        self._doc_repo = document_repo
        self._chunk_repo = chunk_repo
        self._vector_store = vector_store
        self._storage = storage
        self._embedder = embedder or Embedder()
        self._settings = get_settings()

        self._cleaner = TextCleaner()
        self._deduplicator = MinHashDeduplicator(
            num_perm=self._settings.MINHASH_NUM_PERM,
            threshold=self._settings.MINHASH_THRESHOLD,
        )
        self._pipeline = CleaningPipeline(
            min_words=self._settings.QUALITY_MIN_WORDS,
            max_repetition_ratio=self._settings.QUALITY_MAX_REPETITION_RATIO,
        )
        self._chunker = RecursiveChunker(
            chunk_size=self._settings.CHUNK_SIZE,
            chunk_overlap=self._settings.CHUNK_OVERLAP,
        )

    async def ingest_source(self, source: BaseSource, job_id: str | None = None) -> dict:
        """Load from source, clean, deduplicate, embed, store everything."""
        docs = await source.load()
        logger.info("source_loaded", count=len(docs), job_id=job_id)
        return await self.ingest_documents(docs, job_id=job_id)

    async def ingest_documents(self, docs: list[Document], job_id: str | None = None) -> dict:
        """Ingest pre-loaded Document objects."""
        # Clean
        clean_docs = self._cleaner.clean_batch(docs)

        # Deduplicate
        clean_docs = self._deduplicator.deduplicate(clean_docs)

        # Quality filter
        filtered = self._pipeline.run(clean_docs)

        logger.info("cleaned", total=len(docs), after_filter=len(filtered), job_id=job_id)

        indexed = 0
        skipped = 0

        for clean_doc in filtered:
            try:
                await self._ingest_one(clean_doc)
                indexed += 1
            except Exception as exc:
                logger.error("ingest_failed", source=clean_doc.source, error=str(exc))
                skipped += 1

        return {"indexed": indexed, "skipped": skipped, "total": len(docs)}

    async def ingest_text(self, title: str, text: str, source: str = "api", url: str | None = None) -> str:
        """Convenience: ingest a single piece of text and return document_id."""
        doc = Document(
            source=source,
            source_type=SourceType.API,
            url=url,
            title=title,
            text=text,
        )
        result = await self.ingest_documents([doc])
        return result

    async def _ingest_one(self, clean_doc: CleanDocument) -> None:
        from app.db.models.document import Document as DBDocument

        # Check for existing duplicate by content hash (exact)
        import hashlib
        content_hash = hashlib.sha256(clean_doc.text.encode()).hexdigest()
        existing = await self._doc_repo.get_by_hash(content_hash)
        if existing:
            logger.debug("exact_duplicate_skipped", source=clean_doc.source)
            return

        # Persist raw content to object storage
        doc_id = uuid.uuid4()
        raw_key = f"raw/{doc_id}/content.txt"
        clean_key = f"clean/{doc_id}/content.txt"

        await self._storage.put_text(raw_key, clean_doc.text)
        await self._storage.put_text(clean_key, clean_doc.text)

        # Create DB record
        source_type_map = {
            SourceType.WEB: DocumentSource.WEB,
            SourceType.PDF: DocumentSource.PDF,
            SourceType.HUGGINGFACE: DocumentSource.HUGGINGFACE,
            SourceType.COMMON_CRAWL: DocumentSource.COMMON_CRAWL,
            SourceType.API: DocumentSource.API,
            SourceType.UPLOAD: DocumentSource.UPLOAD,
            SourceType.DATABASE: DocumentSource.DATABASE,
        }

        db_doc = DBDocument(
            id=doc_id,
            title=clean_doc.title,
            source=clean_doc.source,
            source_type=source_type_map.get(clean_doc.source_type, DocumentSource.API),
            url=clean_doc.url,
            status=DocumentStatus.PROCESSING,
            content_hash=content_hash,
            language=clean_doc.language,
            word_count=clean_doc.word_count,
            raw_storage_key=raw_key,
            clean_storage_key=clean_key,
            meta=clean_doc.metadata,
        )
        await self._doc_repo.save(db_doc)

        # Chunk + embed
        chunks = self._chunker.chunk(clean_doc)
        if not chunks:
            await self._doc_repo.update(db_doc, status=DocumentStatus.INDEXED, chunk_count=0)
            return

        texts = [c.content for c in chunks]
        embeddings = await self._embedder.embed_async(texts)

        vector_ids = [str(uuid.uuid4()) for _ in chunks]
        metadatas = [
            {
                "document_id": str(doc_id),
                "document_title": clean_doc.title,
                "chunk_index": c.chunk_index,
                "source_type": clean_doc.source_type,
                "url": clean_doc.url or "",
                **{k: v for k, v in c.metadata.items() if isinstance(v, (str, int, float, bool))},
            }
            for c in chunks
        ]

        await self._vector_store.upsert(
            ids=vector_ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        # Save chunks to DB
        from app.db.models.document import DocumentChunk as DBChunk
        db_chunks = [
            DBChunk(
                document_id=doc_id,
                chunk_index=c.chunk_index,
                content=c.content,
                token_count=c.token_count,
                vector_id=vid,
                meta=c.metadata,
            )
            for c, vid in zip(chunks, vector_ids)
        ]
        for chunk in db_chunks:
            self._doc_repo._session.add(chunk)

        await self._doc_repo.update(
            db_doc, status=DocumentStatus.INDEXED, chunk_count=len(chunks)
        )

        logger.info("document_indexed", doc_id=str(doc_id), chunks=len(chunks), source=clean_doc.source)
