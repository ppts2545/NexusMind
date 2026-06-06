"""Structured prompt builder with citation support."""
from __future__ import annotations

from app.rag.vector_store.base import VectorSearchResult


class PromptBuilder:
    """
    Builds LLM prompts from retrieved context chunks.

    Produces both the system prompt (cacheable) and the user message,
    so Anthropic prompt caching can be applied to the context block.
    """

    _SYSTEM = (
        "You are NexusMind, a precise AI research assistant. "
        "Answer the user's question using ONLY the provided context. "
        "If the answer is not in the context, say so clearly. "
        "Cite sources by their [number] at the end of each relevant sentence."
    )

    def build(
        self,
        query: str,
        chunks: list[VectorSearchResult],
        system_override: str | None = None,
    ) -> tuple[str, str]:
        """
        Return (system_prompt, user_message).

        The system prompt contains the context and is suitable for prompt caching.
        The user message contains only the query.
        """
        context_block = self._format_context(chunks)
        system = system_override or self._SYSTEM
        system_with_context = f"{system}\n\n## Context\n\n{context_block}"
        user_message = query
        return system_with_context, user_message

    def _format_context(self, chunks: list[VectorSearchResult]) -> str:
        parts: list[str] = []
        for i, chunk in enumerate(chunks, 1):
            title = chunk.document_title or chunk.document_id
            url = chunk.metadata.get("url", "")
            parts.append(f"[{i}] **{title}**{f' — {url}' if url else ''}\n{chunk.content}")
        return "\n\n".join(parts)

    def format_citations(self, chunks: list[VectorSearchResult]) -> list[dict]:
        return [
            {
                "index": i,
                "document_id": chunk.document_id,
                "document_title": chunk.document_title,
                "chunk_content": chunk.content[:300],
                "score": chunk.score,
                "url": chunk.metadata.get("url"),
            }
            for i, chunk in enumerate(chunks, 1)
        ]
