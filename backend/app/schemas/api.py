from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.core.time import ensure_utc

Ticker = Annotated[str, Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9.\-]+$")]


class UTCModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator(
        "generated_at", "occurs_at", "as_of", "published_at", "price_updated_at",
        check_fields=False,
    )
    @classmethod
    def normalize_dates(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class AssetSummary(UTCModel):
    symbol: Ticker
    name: str
    asset_type: str
    currency: str
    sector: str
    price: Decimal
    change_percent: Decimal


class AssetDetail(AssetSummary):
    market_cap: Decimal
    pe_ratio: Decimal
    dividend_yield: Decimal
    fair_value: Decimal
    technical_signal: Literal["bullish", "neutral", "bearish"]


class RecommendationView(UTCModel):
    symbol: Ticker
    rating: Literal["BUY", "HOLD", "SELL"]
    score: Decimal
    rationale: str
    horizon: str
    generated_at: datetime


class LegacyPositionBase(BaseModel):
    symbol: Ticker
    quantity: Decimal = Field(gt=0, decimal_places=8)
    average_purchase_price: Decimal = Field(gt=0, decimal_places=6)
    purchase_date: date
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    fees: Decimal | None = Field(default=None, ge=0, decimal_places=4)

    @field_validator("symbol", "currency")
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return value.upper()


class LegacyPositionCreate(LegacyPositionBase):
    pass


class LegacyPositionUpdate(BaseModel):
    symbol: str | None = Field(default=None, min_length=1, max_length=16, pattern=r"^[A-Za-z0-9.\-]+$")
    quantity: Decimal | None = Field(default=None, gt=0, decimal_places=8)
    average_purchase_price: Decimal | None = Field(default=None, gt=0, decimal_places=6)
    purchase_date: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    fees: Decimal | None = Field(default=None, ge=0, decimal_places=4)

    @field_validator("symbol", "currency")
    @classmethod
    def normalize_optional_codes(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> "LegacyPositionUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class PositionView(LegacyPositionBase):
    id: int
    sector: str
    geography: str
    current_price: Decimal | None
    current_value: Decimal | None
    invested_capital: Decimal
    unrealized_pnl: Decimal | None
    return_percent: Decimal | None
    is_valued: bool
    price_source: str | None
    price_updated_at: datetime | None
    price_is_stale: bool | None


class AllocationItem(BaseModel):
    label: str
    value: Decimal
    percent: Decimal


class ConcentrationMetrics(BaseModel):
    largest_position_symbol: str
    largest_position_percent: Decimal
    top_three_percent: Decimal


class RiskMetrics(BaseModel):
    historical_volatility_percent: Decimal
    max_drawdown_percent: Decimal
    concentration: ConcentrationMetrics


class CorrelationItem(BaseModel):
    first_symbol: str
    second_symbol: str
    coefficient: Decimal = Field(ge=-1, le=1)


class StressScenario(BaseModel):
    name: str
    shock_percent: Decimal
    projected_value: Decimal
    projected_pnl: Decimal


class NewsImpact(UTCModel):
    title: str
    published_at: datetime
    affected_symbols: list[Ticker]
    impact: Literal["positive", "neutral", "negative"]
    summary: str


class PortfolioView(UTCModel):
    name: str
    base_currency: str
    current_value: Decimal
    invested_capital: Decimal
    recorded_invested_capital: Decimal
    unvalued_positions_count: int
    unrealized_pnl: Decimal
    total_return_percent: Decimal
    as_of: datetime
    positions: list[PositionView]
    allocation_by_asset: list[AllocationItem]
    allocation_by_sector: list[AllocationItem]
    allocation_by_currency: list[AllocationItem]
    risk: RiskMetrics
    correlations: list[CorrelationItem]
    political_and_geographic_risks: list[str]
    stress_scenarios: list[StressScenario]
    news_impacts: list[NewsImpact]
    disclaimer: str


class CSVImportResult(BaseModel):
    imported_count: int
    positions: list[PositionView]
    errors: list[str]


class PoliticalEventView(UTCModel):
    title: str
    region: str
    impact: Literal["high", "medium", "low"]
    summary: str
    affected_assets: list[Ticker]
    occurs_at: datetime


class DashboardSummary(BaseModel):
    portfolio_value: Decimal
    invested_capital: Decimal
    unrealized_pnl: Decimal
    total_return_percent: Decimal
    active_recommendations: int
    high_impact_events: int
    market_status: str


class BacktestRequest(BaseModel):
    symbol: Ticker
    initial_capital: Decimal = Field(default=Decimal("10000.00"), gt=0)
    short_window: int = Field(default=10, ge=1, le=100)
    long_window: int = Field(default=30, ge=3, le=250)
    method: Literal["moving", "hold"] = "moving"
    start_date: date = date(2025, 6, 29)
    end_date: date = date(2026, 6, 29)

    @field_validator("long_window")
    @classmethod
    def validate_windows(cls, value: int, info: ValidationInfo) -> int:
        if value <= info.data.get("short_window", 0):
            raise ValueError("long_window must be greater than short_window")
        return value

    @model_validator(mode="after")
    def validate_period(self) -> "BacktestRequest":
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be earlier than end_date")
        return self


class BacktestResult(BaseModel):
    symbol: Ticker
    method: Literal["moving", "hold"]
    start_date: date
    end_date: date
    final_value: Decimal
    benchmark_final_value: Decimal
    total_return_percent: Decimal
    benchmark_return_percent: Decimal
    max_drawdown_percent: Decimal
    sharpe_ratio: Decimal
    signals: int
    correct_signals: int
    incorrect_signals: int
    dates: list[date]
    strategy_curve: list[Decimal]
    benchmark_curve: list[Decimal]
    note: str
