import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JobStatus(str, Enum):
    PENDING = "pending"
    STARTED = "started"
    SUCCESS = "success"
    FAILURE = "failure"
    RETRY = "retry"
    REVOKED = "revoked"


class JobType(str, Enum):
    CRAWL = "crawl"
    EMBED = "embed"
    DATASET = "dataset"
    REINDEX = "reindex"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    job_type: Mapped[JobType] = mapped_column(String(32), nullable=False)
    status: Mapped[JobStatus] = mapped_column(String(32), default=JobStatus.PENDING)
    # Input parameters for the job (URL, config, etc.)
    params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Output / result summary
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)   # 0–100
    total_items: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_items: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
