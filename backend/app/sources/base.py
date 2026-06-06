"""Base source adapter — every data source implements this interface."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.document import Document


class BaseSource(ABC):
    """
    Pluggable data source adapter.

    Each implementation knows how to load documents from one kind of source
    (web, PDF, HuggingFace dataset, Common Crawl, database…) and normalize
    them into the canonical ``Document`` domain type.
    """

    @abstractmethod
    async def load(self) -> list[Document]:
        """
        Load documents from the source.

        Returns a list of ``Document`` objects ready for the cleaning pipeline.
        Implementations should be idempotent when possible.
        """

    async def stream(self):
        """
        Optional async generator for sources too large to hold in memory.

        Override for sources like Common Crawl where loading all at once
        would exhaust RAM.  Falls back to yielding ``load()`` results.
        """
        for doc in await self.load():
            yield doc
