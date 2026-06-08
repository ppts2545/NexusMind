"""
Source Registry endpoints.

Lets the frontend show which topic categories exist, which domains
are indexed, and trigger a crawl for an entire category with one click.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_job_repo
from app.db.models.job import Job, JobStatus, JobType
from app.rag.intent_classifier import IntentClassifier
from app.repositories.job import JobRepository
from app.sources.registry import REGISTRY, TopicCategory

router = APIRouter(prefix="/sources", tags=["sources"])


# ── Pydantic responses ────────────────────────────────────────────────────────

class SourceEntryOut(BaseModel):
    url: str
    language: str
    description: str
    crawl_depth: int
    crawl_pages: int


class CategoryOut(BaseModel):
    name: str
    description: str
    keywords: list[str]
    sources: list[SourceEntryOut]
    domains: list[str]


class ClassifyOut(BaseModel):
    query: str
    category: str
    confidence: float
    reason: str
    domains: list[str]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[CategoryOut])
async def list_categories():
    """Return all registered topic categories and their trusted sources."""
    return [_cat_out(cat) for cat in REGISTRY.values()]


@router.get("/{category_name}", response_model=CategoryOut)
async def get_category(category_name: str):
    from fastapi import HTTPException
    cat = REGISTRY.get(category_name)
    if cat is None:
        raise HTTPException(status_code=404, detail=f"Category '{category_name}' not found.")
    return _cat_out(cat)


@router.post("/{category_name}/crawl", status_code=202)
async def crawl_category(
    category_name: str,
    job_repo: JobRepository = Depends(get_job_repo),
):
    """
    Trigger a background crawl for every seed URL in a category.
    Returns a job_id to poll for progress.
    """
    from fastapi import HTTPException
    from app.workers.tasks.crawl import crawl_and_ingest

    cat = REGISTRY.get(category_name)
    if cat is None:
        raise HTTPException(status_code=404, detail=f"Category '{category_name}' not found.")

    urls = cat.seed_urls
    max_pages = max(s.crawl_pages for s in cat.sources)
    max_depth = max(s.crawl_depth for s in cat.sources)

    job = Job(
        id=uuid.uuid4(),
        job_type=JobType.CRAWL,
        status=JobStatus.PENDING,
        params={
            "urls": urls,
            "max_depth": max_depth,
            "max_pages": max_pages,
            "category": category_name,
        },
    )
    job = await job_repo.save(job)

    task = crawl_and_ingest.delay(str(job.id), urls, max_depth, max_pages, False)
    await job_repo.update(job, celery_task_id=task.id)

    return {
        "job_id": str(job.id),
        "category": category_name,
        "urls": urls,
        "status": "queued",
    }


@router.post("/classify", response_model=ClassifyOut)
async def classify_query(body: dict):
    """
    Debug endpoint — classify a query and see which category + domains it routes to.
    Useful during development to verify routing works correctly.
    """
    query = body.get("query", "")
    classifier = IntentClassifier()
    result = await classifier.classify_async(query)
    return ClassifyOut(
        query=query,
        category=result.category_name,
        confidence=result.confidence,
        reason=result.reason,
        domains=result.domains,
    )


# ── helpers ───────────────────────────────────────────────────────────────────

def _cat_out(cat: TopicCategory) -> CategoryOut:
    return CategoryOut(
        name=cat.name,
        description=cat.description,
        keywords=cat.keywords,
        domains=cat.domains,
        sources=[
            SourceEntryOut(
                url=s.url,
                language=s.language,
                description=s.description,
                crawl_depth=s.crawl_depth,
                crawl_pages=s.crawl_pages,
            )
            for s in cat.sources
        ],
    )
