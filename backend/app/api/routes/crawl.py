"""Crawl endpoints — submit crawl jobs and check status."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl

from app.api.deps import get_job_repo
from app.db.models.job import JobType, JobStatus as DBJobStatus
from app.repositories.job import JobRepository

router = APIRouter(prefix="/crawl", tags=["crawl"])


class CrawlRequest(BaseModel):
    urls: list[HttpUrl]
    max_depth: int = 2
    max_pages: int = 50
    follow_external: bool = False


class CrawlJobResponse(BaseModel):
    job_id: str
    status: str
    urls: list[str]

    model_config = {"from_attributes": True}


class JobStatusResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    progress: int
    processed_items: int
    total_items: int | None
    result: dict | None
    error_message: str | None
    started_at: str | None
    finished_at: str | None
    created_at: str

    model_config = {"from_attributes": True}


@router.post("/", response_model=CrawlJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_crawl(
    payload: CrawlRequest,
    job_repo: JobRepository = Depends(get_job_repo),
):
    from app.db.models.job import Job

    urls = [str(u) for u in payload.urls]
    job = Job(
        id=uuid.uuid4(),
        job_type=JobType.CRAWL,
        status=DBJobStatus.PENDING,
        params={
            "urls": urls,
            "max_depth": payload.max_depth,
            "max_pages": payload.max_pages,
            "follow_external": payload.follow_external,
        },
    )
    job = await job_repo.save(job)

    # Dispatch to Celery
    from app.workers.tasks.crawl import crawl_and_ingest
    task = crawl_and_ingest.delay(
        str(job.id),
        urls,
        payload.max_depth,
        payload.max_pages,
        payload.follow_external,
    )

    await job_repo.update(job, celery_task_id=task.id)

    return CrawlJobResponse(job_id=str(job.id), status=job.status, urls=urls)


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_crawl_status(
    job_id: uuid.UUID,
    job_repo: JobRepository = Depends(get_job_repo),
):
    job = await job_repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=str(job.id),
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        processed_items=job.processed_items,
        total_items=job.total_items,
        result=job.result,
        error_message=job.error_message,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        created_at=job.created_at.isoformat(),
    )
