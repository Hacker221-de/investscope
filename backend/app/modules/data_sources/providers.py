import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.core.time import utc_now
from app.demo_data import ASSETS
from app.modules.data_sources.contracts import (
    HistoricalBarsResult,
    MarketDataProvider,
    MarketDataProviderError,
    ProviderAssetMetadata,
    ProviderMarketBar,
    ProviderSymbolNotFoundError,
    Timeframe,
    event_time_for,
)
from app.modules.data_sources.gateway import AlphaVantageRequestGateway

logger = logging.getLogger(__name__)


class DemoMarketDataProvider(MarketDataProvider):
    """Deterministic read-only feed for development and tests."""

    name = "demo"

    def _asset(self, symbol: str) -> dict[str, Any]:
        asset = next((item for item in ASSETS if item["symbol"] == symbol.upper()), None)
        if asset is None:
            raise ProviderSymbolNotFoundError(f"Unknown symbol: {symbol}")
        return asset

    async def get_asset_metadata(self, symbol: str) -> ProviderAssetMetadata:
        asset = self._asset(symbol)
        return ProviderAssetMetadata(
            symbol=str(asset["symbol"]), name=str(asset["name"]),
            asset_type=str(asset["asset_type"]), exchange="DEMO",
            sector=str(asset["sector"]), industry=None,
            currency=str(asset["currency"]), provider_symbol=str(asset["symbol"]),
        )

    async def get_historical_bars(
        self, symbol: str, start: date, end: date, timeframe: Timeframe
    ) -> HistoricalBarsResult:
        asset = self._asset(symbol)
        anchor = Decimal(str(asset["price"]))
        received_at = utc_now()
        bars: list[ProviderMarketBar] = []
        day = start
        index = 0
        while day <= end:
            if day.weekday() < 5 and day <= received_at.date():
                drift = Decimal(index % 17 - 8) / Decimal("500")
                close = (anchor * (Decimal("1") + drift)).quantize(Decimal("0.000001"))
                open_value = (close * Decimal("0.998")).quantize(Decimal("0.000001"))
                bars.append(ProviderMarketBar(
                    timeframe=timeframe, event_time=event_time_for(day), open=open_value,
                    high=(close * Decimal("1.006")).quantize(Decimal("0.000001")),
                    low=(open_value * Decimal("0.994")).quantize(Decimal("0.000001")),
                    close=close, adjusted_close=close, volume=1_000_000 + index * 1_000,
                    provider=self.name, published_at=event_time_for(day) + timedelta(hours=23),
                    received_at=received_at,
                ))
                index += 1
            day += timedelta(days=1)
        return HistoricalBarsResult(bars=bars)

    async def get_latest_bar(self, symbol: str) -> ProviderMarketBar | None:
        today = utc_now().date()
        result = await self.get_historical_bars(symbol, today - timedelta(days=7), today, Timeframe.DAY_1)
        return result.bars[-1] if result.bars else None


class AlphaVantageMarketDataProvider(MarketDataProvider):
    """Read-only Alpha Vantage adapter. It never submits orders or connects to a broker."""

    name = "alpha_vantage"
    gateway_managed = True

    def __init__(self, gateway: AlphaVantageRequestGateway) -> None:
        self.gateway = gateway
        self.request_group_id = str(uuid4())

    def begin_request_group(self, request_group_id: str) -> None:
        self.request_group_id = request_group_id

    async def _request(
        self, *, endpoint: str, log_symbol: str, **params: str
    ) -> dict[str, Any]:
        return await self.gateway.request(
            endpoint=endpoint,
            symbol=log_symbol,
            request_group_id=self.request_group_id,
            params={"function": endpoint, **params},
        )

    async def get_asset_metadata(self, symbol: str) -> ProviderAssetMetadata:
        normalized = symbol.upper()
        payload = await self._request(
            endpoint="SYMBOL_SEARCH", log_symbol=normalized, keywords=normalized
        )
        matches = payload.get("bestMatches", [])
        match = next((item for item in matches if item.get("1. symbol", "").upper() == normalized), None)
        if match is None:
            raise ProviderSymbolNotFoundError(f"Unknown symbol: {normalized}")
        return ProviderAssetMetadata(
            symbol=normalized, provider_symbol=str(match["1. symbol"]),
            name=str(match.get("2. name") or normalized),
            asset_type=str(match.get("3. type") or "Unknown"),
            exchange=str(match.get("4. region") or "") or None,
            currency=str(match.get("8. currency") or "USD").upper(),
        )

    def _parse_bar(self, day_text: str, raw: dict[str, Any], received_at: datetime) -> ProviderMarketBar:
        def decimal_field(key: str) -> Decimal | None:
            value = raw.get(key)
            if value in (None, ""):
                return None
            return Decimal(str(value))

        volume_raw = raw.get("5. volume")
        volume = None if volume_raw in (None, "") else int(volume_raw)
        day = date.fromisoformat(day_text)
        return ProviderMarketBar(
            timeframe=Timeframe.DAY_1, event_time=event_time_for(day),
            open=decimal_field("1. open"), high=decimal_field("2. high"),
            low=decimal_field("3. low"), close=decimal_field("4. close"),
            adjusted_close=None, volume=volume, provider=self.name,
            published_at=None, received_at=received_at,
        )

    async def get_historical_bars(
        self, symbol: str, start: date, end: date, timeframe: Timeframe
    ) -> HistoricalBarsResult:
        if timeframe != Timeframe.DAY_1:
            raise MarketDataProviderError("Alpha Vantage adapter currently supports only 1d bars")
        payload = await self._request(
            endpoint="TIME_SERIES_DAILY",
            log_symbol=symbol.upper(),
            symbol=symbol.upper(),
            outputsize="compact",
        )
        series = payload.get("Time Series (Daily)")
        if not isinstance(series, dict):
            raise ProviderSymbolNotFoundError(f"No daily data for {symbol.upper()}")
        received_at = utc_now()
        bars: list[ProviderMarketBar] = []
        rejected = 0
        for day_text, raw in series.items():
            try:
                day = date.fromisoformat(day_text)
                if start <= day <= end and day <= received_at.date():
                    bars.append(self._parse_bar(day_text, raw, received_at))
            except (ValueError, TypeError, InvalidOperation, ValidationError) as error:
                rejected += 1
                logger.warning("Rejected Alpha Vantage row for %s at %s: %s", symbol, day_text, error)
        bars.sort(key=lambda item: item.event_time)
        return HistoricalBarsResult(bars=bars, rejected_count=rejected)

    async def get_latest_bar(self, symbol: str) -> ProviderMarketBar | None:
        payload = await self._request(
            endpoint="GLOBAL_QUOTE",
            log_symbol=symbol.upper(),
            symbol=symbol.upper(),
        )
        quote = payload.get("Global Quote")
        if not isinstance(quote, dict) or not quote.get("07. latest trading day"):
            return None
        raw = {
            "1. open": quote.get("02. open"), "2. high": quote.get("03. high"),
            "3. low": quote.get("04. low"), "4. close": quote.get("05. price"),
            "5. volume": quote.get("06. volume"),
        }
        try:
            return self._parse_bar(str(quote["07. latest trading day"]), raw, utc_now())
        except (ValueError, TypeError, InvalidOperation, ValidationError) as error:
            logger.warning("Rejected latest Alpha Vantage row for %s: %s", symbol, error)
            return None
