from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.time import ensure_utc


class MarketUTCModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator(
        "created_at", "updated_at", "event_time", "published_at", "received_at",
        check_fields=False,
    )
    @classmethod
    def normalize_utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None


class QuoteView(MarketUTCModel):
    close: Decimal
    previous_close: Decimal | None
    change: Decimal | None
    change_percent: Decimal | None
    currency: str
    source: str
    event_time: datetime
    published_at: datetime | None
    received_at: datetime
    is_fetch_stale: bool
    is_market_data_stale: bool
    is_stale: bool


class AssetView(MarketUTCModel):
    id: int
    symbol: str
    name: str
    asset_type: str
    exchange: str | None
    sector: str | None
    industry: str | None
    currency: str
    provider_symbol: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    latest_quote: QuoteView | None = None


class MarketBarView(MarketUTCModel):
    timeframe: str
    event_time: datetime
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    adjusted_close: Decimal | None
    volume: int | None
    provider: str
    published_at: datetime | None
    received_at: datetime


class MarketHistoryView(BaseModel):
    symbol: str
    timeframe: str
    provider: str
    bars: list[MarketBarView]


class LatestMarketView(BaseModel):
    symbol: str
    quote: QuoteView


class MarketSyncView(BaseModel):
    symbol: str
    provider: str
    inserted: int
    updated: int
    rejected: int
    skipped: bool
    reason: str | None
    skip_reason: str | None
    latest_event_time: datetime | None
    latest_received_at: datetime | None
    requests_used_today: int
    daily_limit: int | None
    received_at: datetime


class ProviderMarketDataStatusView(BaseModel):
    configured_provider: str
    available: bool
    requests_used_today: int
    daily_limit: int | None
    remaining_requests: int | None
    last_request_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    data_stale_after_hours: int
