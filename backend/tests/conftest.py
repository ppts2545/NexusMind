"""Shared test fixtures."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_text() -> str:
    return (
        "Retrieval-Augmented Generation (RAG) is an AI framework that combines "
        "information retrieval with text generation. Instead of relying solely on "
        "parametric knowledge encoded in model weights, RAG retrieves relevant "
        "documents from an external knowledge base and uses them as context when "
        "generating responses. This approach reduces hallucinations and allows "
        "models to answer questions about recent or domain-specific information "
        "without retraining.\n\n"
        "The core components of a RAG pipeline are: a retriever that finds relevant "
        "documents using vector similarity search, and a generator (typically a large "
        "language model) that produces answers grounded in the retrieved context."
    )
