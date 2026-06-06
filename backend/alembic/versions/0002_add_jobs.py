"""add jobs table and enhance documents

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enhance documents table ───────────────────────────────────────────────
    op.add_column("documents", sa.Column("source", sa.Text, nullable=True))
    op.add_column("documents", sa.Column("word_count", sa.Integer, server_default="0"))
    op.add_column("documents", sa.Column("raw_storage_key", sa.Text, nullable=True))
    op.add_column("documents", sa.Column("clean_storage_key", sa.Text, nullable=True))
    # Rename source_url → url (more generic)
    op.add_column("documents", sa.Column("url", sa.Text, nullable=True))

    # Back-fill source from source_url
    op.execute("UPDATE documents SET source = COALESCE(source_url, 'unknown'), url = source_url")
    op.alter_column("documents", "source", nullable=False)

    # ── Enhance query_logs table ──────────────────────────────────────────────
    op.add_column("query_logs", sa.Column("used_web_fallback", sa.Boolean, server_default="false"))
    op.add_column("query_logs", sa.Column("confidence_score", sa.Float, nullable=True))

    # ── Jobs table ────────────────────────────────────────────────────────────
    op.create_table(
        "jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("job_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("params", JSONB, nullable=True),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("progress", sa.Integer, server_default="0"),
        sa.Column("total_items", sa.Integer, nullable=True),
        sa.Column("processed_items", sa.Integer, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_jobs_celery_task_id", "jobs", ["celery_task_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_job_type", "jobs", ["job_type"])


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_column("query_logs", "confidence_score")
    op.drop_column("query_logs", "used_web_fallback")
    op.drop_column("documents", "url")
    op.drop_column("documents", "clean_storage_key")
    op.drop_column("documents", "raw_storage_key")
    op.drop_column("documents", "word_count")
    op.drop_column("documents", "source")
