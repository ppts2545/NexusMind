"""Database source — stub interface for pulling documents from SQL databases.

Implement ``_query_rows()`` for your specific schema.
"""
from __future__ import annotations

from abc import abstractmethod
from typing import Any

from app.domain.document import Document, SourceType
from app.sources.base import BaseSource


class DatabaseSource(BaseSource):
    """
    Abstract base for SQL database sources.

    Subclass and implement ``_query_rows()`` to pull from any RDBMS.

    Example::

        class PostgresNewsSource(DatabaseSource):
            async def _query_rows(self) -> list[dict]:
                async with engine.connect() as conn:
                    rows = await conn.execute(text("SELECT id, title, body, url FROM articles"))
                    return [dict(r) for r in rows]

            def _row_to_document(self, row: dict) -> Document:
                return Document(
                    source=f"postgres:articles:{row['id']}",
                    source_type=SourceType.DATABASE,
                    url=row.get("url"),
                    title=row["title"],
                    text=row["body"],
                )
    """

    @abstractmethod
    async def _query_rows(self) -> list[dict[str, Any]]:
        """Return raw rows from the database."""

    def _row_to_document(self, row: dict[str, Any]) -> Document:
        """Convert a raw DB row to a Document. Override for custom mapping."""
        return Document(
            source=f"database:{row.get('id', 'unknown')}",
            source_type=SourceType.DATABASE,
            url=row.get("url"),
            title=str(row.get("title", "Untitled")),
            text=str(row.get("content", row.get("body", row.get("text", "")))),
            metadata={k: v for k, v in row.items() if k not in ("content", "body", "text", "title")},
        )

    async def load(self) -> list[Document]:
        rows = await self._query_rows()
        return [self._row_to_document(row) for row in rows]
