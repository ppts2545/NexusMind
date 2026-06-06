from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "NexusMind"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False

    # ── API ───────────────────────────────────────────────────────────────────
    API_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://nexusmind:nexusmind@localhost:5432/nexusmind"

    # ── Redis / Celery ────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"

    # ── Vector Store ──────────────────────────────────────────────────────────
    VECTOR_STORE: Literal["qdrant", "chroma"] = "qdrant"

    # Qdrant
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION: str = "nexusmind_chunks"

    # ChromaDB (legacy / backward compat)
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    CHROMA_COLLECTION: str = "nexusmind_docs"

    # ── Object Storage ────────────────────────────────────────────────────────
    OBJECT_STORAGE: Literal["local", "s3", "minio"] = "local"

    # Local storage root (used when OBJECT_STORAGE=local)
    LOCAL_STORAGE_ROOT: str = "/tmp/nexusmind_storage"

    # S3 / MinIO — endpoint blank means AWS default
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_REGION: str = "us-east-1"
    S3_BUCKET_RAW: str = "nexusmind-raw"
    S3_BUCKET_CLEAN: str = "nexusmind-clean"
    S3_BUCKET_DATASETS: str = "nexusmind-datasets"

    # ── Embeddings ────────────────────────────────────────────────────────────
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIMENSION: int = 384
    EMBEDDING_BATCH_SIZE: int = 64

    # ── Anthropic / Claude ────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-6"
    MAX_TOKENS: int = 2048

    # ── RAG ───────────────────────────────────────────────────────────────────
    TOP_K_RETRIEVAL: int = 10
    TOP_K_RERANK: int = 5
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    # If best retrieval score < this → trigger web search fallback
    RAG_CONFIDENCE_THRESHOLD: float = 0.35

    # ── Web Search Fallback (Tavily) ──────────────────────────────────────────
    TAVILY_API_KEY: str = ""
    WEB_SEARCH_MAX_RESULTS: int = 5
    WEB_SEARCH_BACKFILL: bool = True

    # ── Crawler ───────────────────────────────────────────────────────────────
    CRAWLER_MAX_DEPTH: int = 3
    CRAWLER_MAX_PAGES: int = 100
    CRAWLER_TIMEOUT: int = 30
    CRAWLER_USER_AGENT: str = "NexusMind-Bot/2.0"

    # ── Training / Datasets ───────────────────────────────────────────────────
    DATASET_OUTPUT_DIR: str = "/tmp/nexusmind_datasets"
    MINHASH_NUM_PERM: int = 128
    MINHASH_THRESHOLD: float = 0.85
    QUALITY_MIN_WORDS: int = 50
    QUALITY_MAX_REPETITION_RATIO: float = 0.3

    # ── HuggingFace ───────────────────────────────────────────────────────────
    HF_TOKEN: str = ""
    HF_CACHE_DIR: str = "/tmp/hf_cache"

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",")]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
