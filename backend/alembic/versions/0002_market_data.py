"""Add persisted read-only market data.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-30 00:00:00+00:00
"""
from collections.abc import Sequence

from alembic import context
from alembic import op
import sqlalchemy as sa

from app.core.database import ExactNumeric

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _canonical_price_points() -> sa.Select[tuple[int, object, object]]:
    price_points = sa.table(
        "price_points",
        sa.column("id", sa.Integer()),
        sa.column("asset_id", sa.Integer()),
        sa.column("timestamp", sa.DateTime(timezone=True)),
        sa.column("close", ExactNumeric(20, 6)),
    )
    source = price_points.alias("source")
    candidate = price_points.alias("candidate")
    latest_id = (
        sa.select(sa.func.max(candidate.c.id))
        .where(
            candidate.c.asset_id == source.c.asset_id,
            candidate.c.timestamp == source.c.timestamp,
        )
        .correlate(source)
        .scalar_subquery()
    )
    return sa.select(source.c.asset_id, source.c.timestamp, source.c.close).where(
        source.c.id == latest_id
    )


def _copy_legacy_price_points() -> None:
    canonical = _canonical_price_points()
    if context.is_offline_mode() or op.get_bind().dialect.name != "sqlite":
        op.execute(
            """
            INSERT INTO market_bars (
                asset_id, timeframe, event_time, close, provider,
                published_at, received_at, inserted_at
            )
            SELECT source.asset_id, '1d', source.timestamp, source.close, 'legacy',
                NULL, source.timestamp, source.timestamp
            FROM price_points AS source
            WHERE source.id = (
                SELECT MAX(candidate.id)
                FROM price_points AS candidate
                WHERE candidate.asset_id = source.asset_id
                  AND candidate.timestamp = source.timestamp
            )
            """
        )
        return

    market_bars = sa.table(
        "market_bars",
        sa.column("asset_id", sa.Integer()),
        sa.column("timeframe", sa.String(length=8)),
        sa.column("event_time", sa.DateTime(timezone=True)),
        sa.column("close", ExactNumeric(20, 8)),
        sa.column("provider", sa.String(length=40)),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("received_at", sa.DateTime(timezone=True)),
        sa.column("inserted_at", sa.DateTime(timezone=True)),
    )
    rows = op.get_bind().execute(canonical).mappings()
    payloads = [
        {
            "asset_id": row["asset_id"],
            "timeframe": "1d",
            "event_time": row["timestamp"],
            "close": row["close"],
            "provider": "legacy",
            "published_at": None,
            "received_at": row["timestamp"],
            "inserted_at": row["timestamp"],
        }
        for row in rows
    ]
    if payloads:
        op.get_bind().execute(market_bars.insert(), payloads)


def upgrade() -> None:
    recreate_assets = "always" if op.get_bind().dialect.name == "sqlite" else "auto"
    with op.batch_alter_table("assets", recreate=recreate_assets) as batch_op:
        batch_op.add_column(sa.Column("exchange", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("industry", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("provider_symbol", sa.String(length=32), nullable=True))
        batch_op.add_column(
            sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            )
        )
    op.create_index("ix_assets_is_active", "assets", ["is_active"])

    op.create_table(
        "market_bars",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", ExactNumeric(20, 8), nullable=True),
        sa.Column("high", ExactNumeric(20, 8), nullable=True),
        sa.Column("low", ExactNumeric(20, 8), nullable=True),
        sa.Column("close", ExactNumeric(20, 8), nullable=True),
        sa.Column("adjusted_close", ExactNumeric(20, 8), nullable=True),
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
    _copy_legacy_price_points()
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
        sa.Column("close", ExactNumeric(20, 6), nullable=False),
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
