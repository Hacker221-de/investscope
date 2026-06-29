"""Initial InvestScope schema.

Revision ID: 0001
Revises:
Create Date: 2026-06-29 00:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("sector", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_assets"),
        sa.UniqueConstraint("symbol", name="uq_assets_symbol"),
    )
    op.create_index("ix_assets_symbol", "assets", ["symbol"])
    op.create_index("ix_assets_asset_type", "assets", ["asset_type"])

    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_portfolios"),
    )
    op.create_table(
        "political_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("region", sa.String(length=80), nullable=False),
        sa.Column("impact", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("occurs_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_political_events"),
    )
    op.create_index("ix_political_events_region", "political_events", ["region"])
    op.create_index("ix_political_events_impact", "political_events", ["impact"])
    op.create_index("ix_political_events_occurs_at", "political_events", ["occurs_at"])

    op.create_table(
        "price_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close", sa.Numeric(20, 6), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_price_points_asset_id_assets", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_price_points"),
    )
    op.create_index("ix_price_points_asset_id", "price_points", ["asset_id"])
    op.create_index("ix_price_points_timestamp", "price_points", ["timestamp"])

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("horizon", sa.String(length=32), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_recommendations_asset_id_assets", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_recommendations"),
    )
    op.create_index("ix_recommendations_asset_id", "recommendations", ["asset_id"])
    op.create_index("ix_recommendations_rating", "recommendations", ["rating"])

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("average_purchase_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("fees", sa.Numeric(20, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], name="fk_positions_portfolio_id_portfolios", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_positions"),
    )
    op.create_index("ix_positions_symbol", "positions", ["symbol"])


def downgrade() -> None:
    op.drop_index("ix_positions_symbol", table_name="positions")
    op.drop_table("positions")
    op.drop_index("ix_recommendations_rating", table_name="recommendations")
    op.drop_index("ix_recommendations_asset_id", table_name="recommendations")
    op.drop_table("recommendations")
    op.drop_index("ix_price_points_timestamp", table_name="price_points")
    op.drop_index("ix_price_points_asset_id", table_name="price_points")
    op.drop_table("price_points")
    op.drop_index("ix_political_events_occurs_at", table_name="political_events")
    op.drop_index("ix_political_events_impact", table_name="political_events")
    op.drop_index("ix_political_events_region", table_name="political_events")
    op.drop_table("political_events")
    op.drop_table("portfolios")
    op.drop_index("ix_assets_asset_type", table_name="assets")
    op.drop_index("ix_assets_symbol", table_name="assets")
    op.drop_table("assets")
