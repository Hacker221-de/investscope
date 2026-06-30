"""Add persisted read-only market data.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-30 00:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("exchange", sa.String(length=32), nullable=True))
    op.add_column("assets", sa.Column("industry", sa.String(length=120), nullable=True))
    op.add_column("assets", sa.Column("provider_symbol", sa.String(length=32), nullable=True))
    op.add_column(
        "assets",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "assets",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_assets_is_active", "assets", ["is_active"])

    op.create_table(
        "market_bars",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(20, 8), nullable=True),
        sa.Column("high", sa.Numeric(20, 8), nullable=True),
        sa.Column("low", sa.Numeric(20, 8), nullable=True),
        sa.Column("close", sa.Numeric(20, 8), nullable=True),
        sa.Column("adjusted_close", sa.Numeric(20, 8), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inserted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "volume IS NULL OR volume >= 0",
            name=op.f("ck_market_bars_volume_nonnegative"),
        ),
        sa.CheckConstraint(
            "high IS NULL OR ((open IS NULL OR high >= open) AND "
            "(close IS NULL OR high >= close) AND (low IS NULL OR high >= low))",
            name=op.f("ck_market_bars_high_valid"),
        ),
        sa.CheckConstraint(
            "low IS NULL OR ((open IS NULL OR low <= open) AND "
            "(close IS NULL OR low <= close) AND (high IS NULL OR low <= high))",
            name=op.f("ck_market_bars_low_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"],
            name="fk_market_bars_asset_id_assets", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_market_bars"),
        sa.UniqueConstraint(
            "asset_id", "timeframe", "event_time", "provider",
            name="uq_market_bars_asset_timeframe_event_provider",
        ),
    )
    op.create_index("ix_market_bars_asset_id", "market_bars", ["asset_id"])
    op.create_index("ix_market_bars_event_time", "market_bars", ["event_time"])
    op.create_index("ix_market_bars_provider", "market_bars", ["provider"])
    op.create_index("ix_market_bars_timeframe", "market_bars", ["timeframe"])
    op.execute(
        """
        INSERT INTO market_bars (
            asset_id, timeframe, event_time, close, provider,
            published_at, received_at, inserted_at
        )
        SELECT DISTINCT ON (asset_id, timestamp)
            asset_id, '1d', timestamp, close, 'legacy',
            NULL, timestamp, timestamp
        FROM price_points
        ORDER BY asset_id, timestamp, id DESC
        """
    )
    op.drop_index("ix_price_points_timestamp", table_name="price_points")
    op.drop_index("ix_price_points_asset_id", table_name="price_points")
    op.drop_table("price_points")


def downgrade() -> None:
    op.drop_index("ix_market_bars_timeframe", table_name="market_bars")
    op.drop_index("ix_market_bars_provider", table_name="market_bars")
    op.drop_index("ix_market_bars_event_time", table_name="market_bars")
    op.drop_index("ix_market_bars_asset_id", table_name="market_bars")
    op.drop_table("market_bars")

    op.create_table(
        "price_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close", sa.Numeric(20, 6), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"],
            name="fk_price_points_asset_id_assets", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_price_points"),
    )
    op.create_index("ix_price_points_asset_id", "price_points", ["asset_id"])
    op.create_index("ix_price_points_timestamp", "price_points", ["timestamp"])

    op.drop_index("ix_assets_is_active", table_name="assets")
    op.drop_column("assets", "updated_at")
    op.drop_column("assets", "is_active")
    op.drop_column("assets", "provider_symbol")
    op.drop_column("assets", "industry")
    op.drop_column("assets", "exchange")
