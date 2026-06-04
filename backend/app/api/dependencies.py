from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.rag_engine import RAGEngine


@lru_cache(maxsize=1)
def get_rag_engine() -> RAGEngine:
    return RAGEngine()
