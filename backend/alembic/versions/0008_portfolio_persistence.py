"""Link portfolio positions to assets and enforce aggregate uniqueness.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-04 00:00:00+00:00
"""
from collections.abc import Sequence
from datetime import UTC, datetime

from alembic import context, op
import sqlalchemy as sa

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _reject_duplicate_positions() -> None:
    duplicates = op.get_bind().execute(sa.text(
        "SELECT portfolio_id, UPPER(symbol) AS normalized_symbol, COUNT(*) AS row_count "
        "FROM positions GROUP BY portfolio_id, UPPER(symbol) HAVING COUNT(*) > 1"
    )).mappings().first()
    if duplicates is not None:
        raise RuntimeError(
            "Cannot migrate duplicate portfolio positions; "
            "deduplicate each portfolio/symbol pair first"
        )


def _ensure_position_assets() -> None:
    connection = op.get_bind()
    missing = connection.execute(sa.text(
        "SELECT UPPER(p.symbol) AS symbol, MIN(p.currency) AS currency "
        "FROM positions AS p "
        "LEFT JOIN assets AS a ON UPPER(a.symbol) = UPPER(p.symbol) "
        "WHERE a.id IS NULL GROUP BY UPPER(p.symbol)"
    )).mappings().all()
    if not missing:
        return

    assets = sa.table(
        "assets",
        sa.column("symbol", sa.String(length=16)),
        sa.column("name", sa.String(length=160)),
        sa.column("asset_type", sa.String(length=32)),
        sa.column("currency", sa.String(length=3)),
        sa.column("provider_symbol", sa.String(length=32)),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    connection.execute(assets.insert(), [
        {
            "symbol": row["symbol"],
            "name": row["symbol"],
            "asset_type": "unknown",
            "currency": row["currency"],
            "provider_symbol": row["symbol"],
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        for row in missing
    ])


def upgrade() -> None:
    if not context.is_offline_mode():
        _reject_duplicate_positions()
        _ensure_position_assets()
    op.add_column("positions", sa.Column("asset_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE positions SET asset_id = ("
        "SELECT assets.id FROM assets WHERE UPPER(assets.symbol) = UPPER(positions.symbol)"
        ")"
    )
    if not context.is_offline_mode():
        unresolved = op.get_bind().execute(
            sa.text("SELECT COUNT(*) FROM positions WHERE asset_id IS NULL")
        ).scalar_one()
        if unresolved:
            raise RuntimeError("Cannot resolve all position assets during migration")

    with op.batch_alter_table("positions") as batch_op:
        batch_op.alter_column(
            "asset_id",
            existing_type=sa.Integer(),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.create_foreign_key(
            "fk_positions_asset_id_assets",
            "assets",
            ["asset_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_unique_constraint(
            "uq_positions_portfolio_asset",
            ["portfolio_id", "asset_id"],
        )
        batch_op.create_index("ix_positions_portfolio_id", ["portfolio_id"])
        batch_op.create_index("ix_positions_asset_id", ["asset_id"])


def downgrade() -> None:
    with op.batch_alter_table("positions") as batch_op:
        batch_op.drop_index("ix_positions_asset_id")
        batch_op.drop_index("ix_positions_portfolio_id")
        batch_op.drop_constraint("uq_positions_portfolio_asset", type_="unique")
        batch_op.drop_constraint("fk_positions_asset_id_assets", type_="foreignkey")
        batch_op.drop_column("asset_id")
