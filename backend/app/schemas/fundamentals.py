from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.time import ensure_utc


class FundamentalUTCModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator(
        "acceptance_datetime", "as_of", "event_time", "filed_at", "imported_at",
        "received_at", "created_at", "updated_at", "filed",
        check_fields=False,
    )
    @classmethod
    def normalize_utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None


class CompanyProfileView(FundamentalUTCModel):
    id: int
    asset_id: int
    provider: str
    cik: str
    legal_name: str
    sic: str | None
    sic_description: str | None
    entity_type: str | None
    state_of_incorporation: str | None
    fiscal_year_end: str | None
    exchanges: list[str]
    tickers: list[str]
    ingestion_method: str
    source_filename: str | None
    imported_at: datetime | None
    received_at: datetime
    created_at: datetime
    updated_at: datetime


class CompanyFilingView(FundamentalUTCModel):
    id: int
    asset_id: int
    provider: str
    accession_number: str
    form: str
    filing_date: date
    report_date: date | None
    acceptance_datetime: datetime | None
    primary_document: str | None
    primary_doc_description: str | None
    file_number: str | None
    film_number: str | None
    items: str | None
    is_inline_xbrl: bool
    is_xbrl: bool
    is_amendment: bool
    amended_form: str | None
    filing_url: str | None
    ingestion_method: str
    source_filename: str | None
    imported_at: datetime | None
    received_at: datetime
    created_at: datetime


class FinancialFactView(FundamentalUTCModel):
    id: int
    asset_id: int
    provider: str
    taxonomy: str
    concept: str
    label: str | None
    description: str | None
    normalized_metric: str | None
    unit: str
    value: Decimal
    period_start: date | None
    period_end: date
    filed_at: datetime
    frame: str | None
    fiscal_year: int | None
    fiscal_period: str | None
    form: str
    accession_number: str
    is_instant: bool
    period_type: str
    ingestion_method: str
    source_filename: str | None
    imported_at: datetime | None
    received_at: datetime
    created_at: datetime


class FundamentalSyncView(FundamentalUTCModel):
    symbol: str
    cik: str
    provider: str
    profile_created: int
    profile_updated: int
    filings_inserted: int
    filings_updated: int
    facts_inserted: int
    facts_skipped: int
    facts_rejected: int
    skipped: bool
    skip_reason: str | None
    warning: str | None
    received_at: datetime


class FundamentalFactProvenanceView(FundamentalUTCModel):
    id: int
    value: Decimal
    unit: str
    taxonomy: str
    concept: str
    period_start: date | None
    period_end: date
    period_type: str
    fiscal_year: int | None
    fiscal_period: str | None
    frame: str | None
    filed_at: datetime
    form: str
    accession_number: str
    acceptance_datetime: datetime | None
    filing_url: str | None
    is_amendment: bool
    ingestion_method: str
    source_filename: str | None


class FundamentalCalculationComponentView(FundamentalUTCModel):
    id: int
    identity: str
    metric: str
    value: Decimal
    unit: str
    start: date | None
    end: date
    fiscal_year: int | None
    fiscal_period: str | None
    form: str
    accession_number: str
    filed: datetime
    frame: str | None
    is_amendment: bool
    is_repeated_comparative: bool
    source_filename: str | None
    ingestion_method: str


class FundamentalMetricPointView(BaseModel):
    metric: str
    value: Decimal | None
    unit: str | None
    period_start: date | None
    period_end: date
    period_type: str
    fiscal_year: int | None
    fiscal_period: str | None
    frame: str | None
    selected_fact: FundamentalFactProvenanceView | None
    alternative_facts: list[FundamentalFactProvenanceView]
    source_facts: list[FundamentalFactProvenanceView]
    calculation_components: list[FundamentalCalculationComponentView]
    selection_reason: str
    is_repeated_comparative: bool
    is_restated: bool
    has_conflict: bool
    warnings: list[str]
    calculation: str | None
    derived: bool
    derivation_method: str | None
    confidence: str | None
    status: str


class FundamentalPeriodView(BaseModel):
    period_start: date
    period_end: date
    period_type: str
    fiscal_year: int | None
    fiscal_period: str | None
    frame: str | None


class FundamentalMarketPriceView(FundamentalUTCModel):
    value: Decimal
    provider: str
    event_time: datetime
    received_at: datetime
    is_stale: bool


class FundamentalCompletenessView(BaseModel):
    status: str
    available_metrics: int
    expected_metrics: int
    ratio: Decimal
    missing_metrics: list[str]


class FundamentalMetricsView(FundamentalUTCModel):
    symbol: str
    provider: str
    period_type: str
    as_of: datetime
    periods: list[FundamentalPeriodView]
    metrics: dict[str, list[FundamentalMetricPointView]]
    market_price: FundamentalMarketPriceView | None
    warnings: list[str]
    completeness: FundamentalCompletenessView
