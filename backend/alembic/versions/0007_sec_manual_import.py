"""Add SEC manual JSON ingestion metadata.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-02 00:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("company_profiles", "company_filings", "financial_facts")


def upgrade() -> None:
    for table_name in TABLES:
        op.add_column(
            table_name,
            sa.Column(
                "ingestion_method",
                sa.String(length=16),
                server_default="api",
                nullable=False,
            ),
        )
        op.add_column(
            table_name,
            sa.Column("source_filename", sa.String(length=500), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    for table_name in reversed(TABLES):
        op.drop_column(table_name, "imported_at")
        op.drop_column(table_name, "source_filename")
        op.drop_column(table_name, "ingestion_method")
