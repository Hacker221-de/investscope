"""Add provider request accounting.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-30 00:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_request_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("successful", sa.Boolean(), nullable=False),
        sa.Column("error_type", sa.String(length=80), nullable=True),
        sa.Column("request_group_id", sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_provider_request_logs"),
    )
    op.create_index(
        "ix_provider_request_logs_provider", "provider_request_logs", ["provider"]
    )
    op.create_index(
        "ix_provider_request_logs_symbol", "provider_request_logs", ["symbol"]
    )
    op.create_index(
        "ix_provider_request_logs_requested_at", "provider_request_logs", ["requested_at"]
    )
    op.create_index(
        "ix_provider_request_logs_successful", "provider_request_logs", ["successful"]
    )
    op.create_index(
        "ix_provider_request_logs_request_group_id",
        "provider_request_logs",
        ["request_group_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_request_logs_request_group_id", table_name="provider_request_logs")
    op.drop_index("ix_provider_request_logs_successful", table_name="provider_request_logs")
    op.drop_index("ix_provider_request_logs_requested_at", table_name="provider_request_logs")
    op.drop_index("ix_provider_request_logs_symbol", table_name="provider_request_logs")
    op.drop_index("ix_provider_request_logs_provider", table_name="provider_request_logs")
    op.drop_table("provider_request_logs")
