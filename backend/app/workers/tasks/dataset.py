"""Dataset build background task."""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.workers.celery_app import celery_app


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=2, name="nexusmind.build_dataset")
def build_dataset(self, job_id: str, config_dict: dict) -> dict[str, Any]:
    async def _run_async():
        from app.db.session import AsyncSessionLocal
        from app.domain.dataset import DatasetConfig
        from app.repositories.job import JobRepository
        from app.services.dataset import DatasetService
        from app.storage.s3 import make_storage_from_settings

        async with AsyncSessionLocal() as session:
            job_repo = JobRepository(session)
            await job_repo.mark_started(uuid.UUID(job_id), self.request.id)

            try:
                config = DatasetConfig(**config_dict)
                storage = make_storage_from_settings()
                service = DatasetService(storage)
                result = await service.build(config, job_id=job_id)

                result_dict = {
                    "name": result.name,
                    "output_path": result.output_path,
                    "total_samples": result.total_samples,
                }
                await job_repo.mark_success(uuid.UUID(job_id), result_dict, result.total_samples)
                return result_dict

            except Exception as exc:
                await job_repo.mark_failed(uuid.UUID(job_id), str(exc))
                raise self.retry(exc=exc)

    try:
        return _run(_run_async())
    except Exception as exc:
        raise self.retry(exc=exc)
