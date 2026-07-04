"""Add SEC EDGAR fundamental data.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-01 00:00:00+00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

from app.core.database import ExactNumeric

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("cik", sa.String(length=10), nullable=True))
    op.add_column("assets", sa.Column("sec_entity_name", sa.String(length=240), nullable=True))
    op.add_column("assets", sa.Column("sec_exchange", sa.String(length=80), nullable=True))
    op.add_column("assets", sa.Column("sec_last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_assets_cik", "assets", ["cik"])

    op.create_table(
        "company_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("legal_name", sa.String(length=240), nullable=False),
        sa.Column("sic", sa.String(length=8), nullable=True),
        sa.Column("sic_description", sa.String(length=240), nullable=True),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("state_of_incorporation", sa.String(length=16), nullable=True),
        sa.Column("fiscal_year_end", sa.String(length=4), nullable=True),
        sa.Column("exchanges", sa.JSON(), nullable=False),
        sa.Column("tickers", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_company_profiles_asset_id_assets", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_company_profiles"),
        sa.UniqueConstraint("asset_id", "provider", name="uq_company_profiles_asset_provider"),
    )
    op.create_index("ix_company_profiles_asset_id", "company_profiles", ["asset_id"])
    op.create_index("ix_company_profiles_provider", "company_profiles", ["provider"])
    op.create_index("ix_company_profiles_cik", "company_profiles", ["cik"])

    op.create_table(
        "company_filings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("accession_number", sa.String(length=24), nullable=False),
        sa.Column("form", sa.String(length=16), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("acceptance_datetime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("primary_document", sa.String(length=240), nullable=True),
        sa.Column("primary_doc_description", sa.String(length=500), nullable=True),
        sa.Column("file_number", sa.String(length=80), nullable=True),
        sa.Column("film_number", sa.String(length=80), nullable=True),
        sa.Column("items", sa.String(length=500), nullable=True),
        sa.Column("is_inline_xbrl", sa.Boolean(), nullable=False),
        sa.Column("is_xbrl", sa.Boolean(), nullable=False),
        sa.Column("is_amendment", sa.Boolean(), nullable=False),
        sa.Column("amended_form", sa.String(length=16), nullable=True),
        sa.Column("filing_url", sa.String(length=600), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_company_filings_asset_id_assets", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_company_filings"),
        sa.UniqueConstraint("provider", "accession_number", name="uq_company_filings_provider_accession"),
    )
    for column in ("asset_id", "provider", "accession_number", "form", "filing_date", "acceptance_datetime", "is_amendment"):
        op.create_index(f"ix_company_filings_{column}", "company_filings", [column])

    op.create_table(
        "financial_facts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("taxonomy", sa.String(length=80), nullable=False),
        sa.Column("concept", sa.String(length=180), nullable=False),
        sa.Column("label", sa.String(length=300), nullable=True),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("normalized_metric", sa.String(length=80), nullable=True),
        sa.Column("unit", sa.String(length=80), nullable=False),
        sa.Column("value", ExactNumeric(38, 10), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("frame", sa.String(length=80), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_period", sa.String(length=16), nullable=True),
        sa.Column("form", sa.String(length=16), nullable=False),
        sa.Column("accession_number", sa.String(length=24), nullable=False),
        sa.Column("is_instant", sa.Boolean(), nullable=False),
        sa.Column("period_type", sa.String(length=24), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fact_identity", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name="fk_financial_facts_asset_id_assets", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_financial_facts"),
        sa.UniqueConstraint("fact_identity", name="uq_financial_facts_identity"),
    )
    for column in ("asset_id", "provider", "taxonomy", "concept", "normalized_metric", "period_end", "filed_at", "fiscal_year", "fiscal_period", "form", "accession_number", "is_instant", "period_type"):
        op.create_index(f"ix_financial_facts_{column}", "financial_facts", [column])


def downgrade() -> None:
    for column in reversed(("asset_id", "provider", "taxonomy", "concept", "normalized_metric", "period_end", "filed_at", "fiscal_year", "fiscal_period", "form", "accession_number", "is_instant", "period_type")):
        op.drop_index(f"ix_financial_facts_{column}", table_name="financial_facts")
    op.drop_table("financial_facts")
    for column in reversed(("asset_id", "provider", "accession_number", "form", "filing_date", "acceptance_datetime", "is_amendment")):
        op.drop_index(f"ix_company_filings_{column}", table_name="company_filings")
    op.drop_table("company_filings")
    op.drop_index("ix_company_profiles_cik", table_name="company_profiles")
    op.drop_index("ix_company_profiles_provider", table_name="company_profiles")
    op.drop_index("ix_company_profiles_asset_id", table_name="company_profiles")
    op.drop_table("company_profiles")
    op.drop_index("ix_assets_cik", table_name="assets")
    op.drop_column("assets", "sec_last_synced_at")
    op.drop_column("assets", "sec_exchange")
    op.drop_column("assets", "sec_entity_name")
    op.drop_column("assets", "cik")
