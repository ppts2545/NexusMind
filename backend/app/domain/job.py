from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    STARTED = "started"
    SUCCESS = "success"
    FAILURE = "failure"
    RETRY = "retry"


class JobType(str, Enum):
    CRAWL = "crawl"
    EMBED = "embed"
    DATASET = "dataset"
    REINDEX = "reindex"


class Job(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    celery_task_id: str | None = None
    job_type: JobType
    status: JobStatus = JobStatus.PENDING
    params: dict = Field(default_factory=dict)
    result: dict | None = None
    error_message: str | None = None
    progress: int = 0
    total_items: int | None = None
    processed_items: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
