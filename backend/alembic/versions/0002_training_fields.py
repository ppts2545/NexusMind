"""add training tables and retrieved_chunks column

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-03
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
    op.add_column("query_logs", sa.Column("retrieved_chunks", JSONB, nullable=True))
    op.add_column("query_logs", sa.Column("used_for_training", sa.Boolean, nullable=False, server_default="false"))

    op.create_table(
        "training_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("base_model", sa.String(256), nullable=False),
        sa.Column("output_model_path", sa.Text, nullable=True),
        sa.Column("training_samples", sa.Integer, nullable=False, server_default="0"),
        sa.Column("epochs", sa.Integer, nullable=False, server_default="0"),
        sa.Column("train_loss", sa.Float, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("reindex_completed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("training_runs")
    op.drop_column("query_logs", "used_for_training")
    op.drop_column("query_logs", "retrieved_chunks")
