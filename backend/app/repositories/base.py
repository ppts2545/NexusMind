"""Generic repository base — thin async SQLAlchemy wrapper."""
from __future__ import annotations

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, id: UUID) -> ModelT | None:
        result = await self._session.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def get_or_raise(self, id: UUID) -> ModelT:
        obj = await self.get(id)
        if obj is None:
            raise ValueError(f"{self.model.__name__} {id} not found")
        return obj

    async def list(self, offset: int = 0, limit: int = 20, **filters: Any) -> list[ModelT]:
        stmt = select(self.model)
        for attr, value in filters.items():
            stmt = stmt.where(getattr(self.model, attr) == value)
        stmt = stmt.offset(offset).limit(limit).order_by(self.model.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, **filters: Any) -> int:
        from sqlalchemy import func
        stmt = select(func.count()).select_from(self.model)
        for attr, value in filters.items():
            stmt = stmt.where(getattr(self.model, attr) == value)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def save(self, obj: ModelT) -> ModelT:
        self._session.add(obj)
        await self._session.commit()
        await self._session.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self._session.delete(obj)
        await self._session.commit()

    async def update(self, obj: ModelT, **fields: Any) -> ModelT:
        for key, value in fields.items():
            setattr(obj, key, value)
        await self._session.commit()
        await self._session.refresh(obj)
        return obj
