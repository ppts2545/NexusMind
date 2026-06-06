from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.db.models.job import Job, JobStatus, JobType
from app.repositories.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    model = Job

    async def get_by_celery_id(self, celery_task_id: str) -> Job | None:
        result = await self._session.execute(
            select(Job).where(Job.celery_task_id == celery_task_id)
        )
        return result.scalar_one_or_none()

    async def list_by_type(self, job_type: JobType, limit: int = 50) -> list[Job]:
        result = await self._session.execute(
            select(Job)
            .where(Job.job_type == job_type)
            .order_by(Job.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_started(self, job_id: UUID, celery_task_id: str) -> Job:
        job = await self.get_or_raise(job_id)
        job.status = JobStatus.STARTED
        job.celery_task_id = celery_task_id
        job.started_at = datetime.now(timezone.utc)
        await self._session.commit()
        await self._session.refresh(job)
        return job

    async def mark_success(self, job_id: UUID, result: dict, processed: int) -> Job:
        job = await self.get_or_raise(job_id)
        job.status = JobStatus.SUCCESS
        job.result = result
        job.processed_items = processed
        job.progress = 100
        job.finished_at = datetime.now(timezone.utc)
        await self._session.commit()
        await self._session.refresh(job)
        return job

    async def mark_failed(self, job_id: UUID, error: str) -> Job:
        job = await self.get_or_raise(job_id)
        job.status = JobStatus.FAILURE
        job.error_message = error
        job.finished_at = datetime.now(timezone.utc)
        await self._session.commit()
        await self._session.refresh(job)
        return job

    async def update_progress(self, job_id: UUID, processed: int, total: int | None = None) -> None:
        job = await self.get_or_raise(job_id)
        job.processed_items = processed
        if total is not None:
            job.total_items = total
        if total:
            job.progress = min(99, int(processed / total * 100))
        await self._session.commit()
