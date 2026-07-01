"""Add detailed provider request timing.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-01 00:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "provider_request_logs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "provider_request_logs",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "provider_request_logs",
        sa.Column("retry_after_seconds", sa.Integer(), nullable=True),
    )
    op.execute(
        "UPDATE provider_request_logs "
        "SET started_at = requested_at, completed_at = requested_at"
    )
    op.alter_column("provider_request_logs", "started_at", nullable=False)
    op.alter_column("provider_request_logs", "completed_at", nullable=False)
    op.create_index(
        "ix_provider_request_logs_started_at",
        "provider_request_logs",
        ["started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_request_logs_started_at", table_name="provider_request_logs")
    op.drop_column("provider_request_logs", "retry_after_seconds")
    op.drop_column("provider_request_logs", "completed_at")
    op.drop_column("provider_request_logs", "started_at")
