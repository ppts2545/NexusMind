"""
Query Intent Classifier

Uses Claude to classify which topic category a user query belongs to,
then returns the matching Source Registry entry so the retriever can
filter results to only trusted, relevant domains.
"""
from __future__ import annotations

import json

import anthropic

from app.core.config import get_settings
from app.core.logging import get_logger
from app.sources.registry import REGISTRY, TopicCategory, all_categories

logger = get_logger(__name__)
settings = get_settings()


# Build the category list once — injected into the system prompt
_CATEGORY_LIST = "\n".join(
    f'- "{cat.name}": {cat.description}'
    for cat in all_categories()
)

_SYSTEM_PROMPT = f"""You are a query intent classifier for a RAG system.
Given a user query, identify which ONE topic category it belongs to.

Categories:
{_CATEGORY_LIST}

Respond with valid JSON only — no explanation, no markdown:
{{
  "category": "<category_name>",
  "confidence": <0.0–1.0>,
  "reason": "<one sentence>"
}}

If the query fits no specific category, use "general".
"""


class IntentClassifier:
    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def classify(self, query: str) -> ClassificationResult:
        """Synchronous classification — safe to call from Celery workers."""
        try:
            response = self._client.messages.create(
                model="claude-haiku-4-5-20251001",   # fastest + cheapest model for classification
                max_tokens=128,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": query}],
            )
            raw = response.content[0].text.strip()
            data = json.loads(raw)

            category_name = data.get("category", "general")
            confidence = float(data.get("confidence", 0.5))
            reason = data.get("reason", "")

            category = REGISTRY.get(category_name) or REGISTRY["general"]
            logger.info(
                "intent_classified",
                query=query[:60],
                category=category_name,
                confidence=confidence,
            )
            return ClassificationResult(
                category=category,
                confidence=confidence,
                reason=reason,
            )

        except Exception as exc:
            logger.warning("intent_classification_failed", error=str(exc))
            return ClassificationResult(
                category=REGISTRY["general"],
                confidence=0.0,
                reason="classification failed — falling back to general",
            )

    async def classify_async(self, query: str) -> "ClassificationResult":
        """Async version for use inside FastAPI route handlers."""
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(None, self.classify, query)


class ClassificationResult:
    def __init__(self, category: TopicCategory, confidence: float, reason: str) -> None:
        self.category = category
        self.confidence = confidence
        self.reason = reason

    @property
    def domains(self) -> list[str]:
        return self.category.domains

    @property
    def category_name(self) -> str:
        return self.category.name

    def should_auto_crawl(self, indexed_domains: set[str]) -> bool:
        """True if none of the category's domains have been indexed yet."""
        return not any(d in indexed_domains for d in self.domains)

    def to_dict(self) -> dict:
        return {
            "category": self.category_name,
            "confidence": self.confidence,
            "reason": self.reason,
            "domains": self.domains,
        }
