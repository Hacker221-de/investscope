"""Add persistent SEC ticker to CIK cache.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-02 00:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sec_ticker_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("legal_name", sa.String(length=240), nullable=False),
        sa.Column("exchange", sa.String(length=80), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_sec_ticker_cache"),
        sa.UniqueConstraint("symbol", name="uq_sec_ticker_cache_symbol"),
    )
    op.create_index("ix_sec_ticker_cache_symbol", "sec_ticker_cache", ["symbol"])
    op.create_index("ix_sec_ticker_cache_cik", "sec_ticker_cache", ["cik"])
    op.create_index("ix_sec_ticker_cache_fetched_at", "sec_ticker_cache", ["fetched_at"])


def downgrade() -> None:
    op.drop_index("ix_sec_ticker_cache_fetched_at", table_name="sec_ticker_cache")
    op.drop_index("ix_sec_ticker_cache_cik", table_name="sec_ticker_cache")
    op.drop_index("ix_sec_ticker_cache_symbol", table_name="sec_ticker_cache")
    op.drop_table("sec_ticker_cache")
