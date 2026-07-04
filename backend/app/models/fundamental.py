from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, ExactNumeric, UTCDateTime
from app.core.time import utc_now


class CompanyProfile(Base):
    __tablename__ = "company_profiles"
    __table_args__ = (
        UniqueConstraint("asset_id", "provider", name="uq_company_profiles_asset_provider"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    cik: Mapped[str] = mapped_column(String(10), index=True)
    legal_name: Mapped[str] = mapped_column(String(240))
    sic: Mapped[str | None] = mapped_column(String(8))
    sic_description: Mapped[str | None] = mapped_column(String(240))
    entity_type: Mapped[str | None] = mapped_column(String(80))
    state_of_incorporation: Mapped[str | None] = mapped_column(String(16))
    fiscal_year_end: Mapped[str | None] = mapped_column(String(4))
    exchanges: Mapped[list[str]] = mapped_column(JSON, default=list)
    tickers: Mapped[list[str]] = mapped_column(JSON, default=list)
    ingestion_method: Mapped[str] = mapped_column(String(16), default="api")
    source_filename: Mapped[str | None] = mapped_column(String(500))
    imported_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    received_at: Mapped[datetime] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)

    asset: Mapped["Asset"] = relationship(back_populates="company_profiles")


class CompanyFiling(Base):
    __tablename__ = "company_filings"
    __table_args__ = (
        UniqueConstraint("provider", "accession_number", name="uq_company_filings_provider_accession"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    accession_number: Mapped[str] = mapped_column(String(24), index=True)
    form: Mapped[str] = mapped_column(String(16), index=True)
    filing_date: Mapped[date] = mapped_column(Date, index=True)
    report_date: Mapped[date | None] = mapped_column(Date)
    acceptance_datetime: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    primary_document: Mapped[str | None] = mapped_column(String(240))
    primary_doc_description: Mapped[str | None] = mapped_column(String(500))
    file_number: Mapped[str | None] = mapped_column(String(80))
    film_number: Mapped[str | None] = mapped_column(String(80))
    items: Mapped[str | None] = mapped_column(String(500))
    is_inline_xbrl: Mapped[bool] = mapped_column(Boolean, default=False)
    is_xbrl: Mapped[bool] = mapped_column(Boolean, default=False)
    is_amendment: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    amended_form: Mapped[str | None] = mapped_column(String(16))
    filing_url: Mapped[str | None] = mapped_column(String(600))
    ingestion_method: Mapped[str] = mapped_column(String(16), default="api")
    source_filename: Mapped[str | None] = mapped_column(String(500))
    imported_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    received_at: Mapped[datetime] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    asset: Mapped["Asset"] = relationship(back_populates="filings")


class FinancialFact(Base):
    __tablename__ = "financial_facts"
    __table_args__ = (
        UniqueConstraint("fact_identity", name="uq_financial_facts_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    taxonomy: Mapped[str] = mapped_column(String(80), index=True)
    concept: Mapped[str] = mapped_column(String(180), index=True)
    label: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(String(2000))
    normalized_metric: Mapped[str | None] = mapped_column(String(80), index=True)
    unit: Mapped[str] = mapped_column(String(80))
    value: Mapped[Decimal] = mapped_column(ExactNumeric(38, 10))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    filed_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    frame: Mapped[str | None] = mapped_column(String(80))
    fiscal_year: Mapped[int | None] = mapped_column(index=True)
    fiscal_period: Mapped[str | None] = mapped_column(String(16), index=True)
    form: Mapped[str] = mapped_column(String(16), index=True)
    accession_number: Mapped[str] = mapped_column(String(24), index=True)
    is_instant: Mapped[bool] = mapped_column(Boolean, index=True)
    period_type: Mapped[str] = mapped_column(String(24), index=True)
    ingestion_method: Mapped[str] = mapped_column(String(16), default="api")
    source_filename: Mapped[str | None] = mapped_column(String(500))
    imported_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    received_at: Mapped[datetime] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    fact_identity: Mapped[str] = mapped_column(String(64))

    asset: Mapped["Asset"] = relationship(back_populates="financial_facts")


class SecTickerCache(Base):
    __tablename__ = "sec_ticker_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    cik: Mapped[str] = mapped_column(String(10), index=True)
    legal_name: Mapped[str] = mapped_column(String(240))
    exchange: Mapped[str | None] = mapped_column(String(80))
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)
