from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import crawl, datasets, documents, health, search
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(debug=settings.DEBUG)

    # Ensure vector store collection exists
    from app.api.deps import _vector_store, _embedder
    vs = _vector_store()
    if not await vs.collection_exists():
        await vs.create_collection(dimension=_embedder().dimension)

    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Production-grade AI Knowledge Platform. "
        "Supports RAG, multi-source ingestion, web search fallback, "
        "and training data pipeline."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(crawl.router, prefix=settings.API_PREFIX)
app.include_router(documents.router, prefix=settings.API_PREFIX)
app.include_router(search.router, prefix=settings.API_PREFIX)
app.include_router(datasets.router, prefix=settings.API_PREFIX)
