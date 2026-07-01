from abc import ABC, abstractmethod
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.time import ensure_utc


class Timeframe(StrEnum):
    DAY_1 = "1d"


class ProviderAssetMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str = Field(pattern=r"^[A-Z0-9.\-]+$", max_length=16)
    name: str
    asset_type: str
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    provider_symbol: str


class ProviderMarketBar(BaseModel):
    model_config = ConfigDict(frozen=True)

    timeframe: Timeframe
    event_time: datetime
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    adjusted_close: Decimal | None = None
    volume: int | None = Field(default=None, ge=0)
    provider: str
    published_at: datetime | None = None
    received_at: datetime

    @field_validator("event_time", "published_at", "received_at")
    @classmethod
    def utc_datetimes(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None

    @model_validator(mode="after")
    def valid_ohlc(self) -> "ProviderMarketBar":
        if self.high is not None:
            compared = [value for value in (self.open, self.close, self.low) if value is not None]
            if any(self.high < value for value in compared):
                raise ValueError("high must be greater than or equal to open, close and low")
        if self.low is not None:
            compared = [value for value in (self.open, self.close, self.high) if value is not None]
            if any(self.low > value for value in compared):
                raise ValueError("low must be less than or equal to open, close and high")
        return self


class HistoricalBarsResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    bars: list[ProviderMarketBar]
    rejected_count: int = Field(default=0, ge=0)


class MarketDataProvider(ABC):
    name: str
    gateway_managed: bool = False

    def begin_request_group(self, request_group_id: str) -> None:
        """Set request correlation for providers with a managed transport."""

    @abstractmethod
    async def get_asset_metadata(self, symbol: str) -> ProviderAssetMetadata:
        raise NotImplementedError

    @abstractmethod
    async def get_historical_bars(
        self, symbol: str, start: date, end: date, timeframe: Timeframe
    ) -> HistoricalBarsResult:
        raise NotImplementedError

    @abstractmethod
    async def get_latest_bar(self, symbol: str) -> ProviderMarketBar | None:
        raise NotImplementedError


class MarketDataProviderError(RuntimeError):
    pass


class ProviderConfigurationError(MarketDataProviderError):
    pass


class ProviderTimeoutError(MarketDataProviderError):
    pass


class ProviderRateLimitError(MarketDataProviderError):
    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: int | None = None,
        requests_used_today: int | None = None,
        daily_limit: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
        self.requests_used_today = requests_used_today
        self.daily_limit = daily_limit


class ProviderBurstLimitError(ProviderRateLimitError):
    pass


class ProviderDailyLimitError(ProviderRateLimitError):
    pass


class ProviderInvalidRequestError(MarketDataProviderError):
    pass


class ProviderSymbolNotFoundError(MarketDataProviderError):
    pass


def event_time_for(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)
