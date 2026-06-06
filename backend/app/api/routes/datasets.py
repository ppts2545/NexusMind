"""Dataset build endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.deps import get_dataset_service, get_job_repo
from app.domain.dataset import DatasetConfig, DatasetFormat, DatasetType
from app.repositories.job import JobRepository
from app.services.dataset import DatasetService

router = APIRouter(prefix="/datasets", tags=["datasets"])


class DatasetBuildRequest(BaseModel):
    name: str
    dataset_type: DatasetType = DatasetType.PRETRAINING
    output_format: DatasetFormat = DatasetFormat.JSONL
    min_words: int = 50
    max_words: int = 100_000
    languages: list[str] = ["en"]
    deduplicate: bool = True
    source_types: list[str] | None = None


class DatasetBuildResponse(BaseModel):
    job_id: str
    status: str
    name: str


@router.post("/build", response_model=DatasetBuildResponse, status_code=status.HTTP_202_ACCEPTED)
async def build_dataset(
    payload: DatasetBuildRequest,
    job_repo: JobRepository = Depends(get_job_repo),
):
    from app.db.models.job import Job, JobType, JobStatus

    job = Job(
        id=uuid.uuid4(),
        job_type=JobType.DATASET,
        status=JobStatus.PENDING,
        params=payload.model_dump(),
    )
    job = await job_repo.save(job)

    from app.workers.tasks.dataset import build_dataset as build_task
    task = build_task.delay(str(job.id), payload.model_dump())
    await job_repo.update(job, celery_task_id=task.id)

    return DatasetBuildResponse(job_id=str(job.id), status=job.status, name=payload.name)
