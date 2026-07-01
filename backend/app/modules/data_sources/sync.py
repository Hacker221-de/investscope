from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from uuid import uuid4
from typing import TypeVar

from sqlalchemy.orm import Session

from app.modules.data_sources.contracts import MarketDataProvider, Timeframe
from app.modules.data_sources.limits import ProviderRequestCoordinator
from app.core.time import utc_now
from app.repositories import MarketDataRepository

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class SyncResult:
    symbol: str
    provider: str
    inserted: int
    updated: int
    rejected: int
    received_at: datetime


async def synchronize_market_data(
    session: Session,
    provider: MarketDataProvider,
    symbol: str,
    start: date,
    end: date,
    timeframe: Timeframe,
    coordinator: ProviderRequestCoordinator,
) -> SyncResult:
    repository = MarketDataRepository(session)
    normalized = symbol.upper()
    asset = repository.get_asset(normalized)
    request_group_id = str(uuid4())
    provider.begin_request_group(request_group_id)

    async def provider_request(
        endpoint: str, operation: Callable[[], Awaitable[T]]
    ) -> T:
        if provider.gateway_managed:
            return await operation()
        return await coordinator.request(
            provider=provider.name,
            endpoint=endpoint,
            symbol=normalized,
            request_group_id=request_group_id,
            operation=operation,
        )

    metadata = None
    if asset is None:
        metadata = await provider_request(
            "SYMBOL_SEARCH", lambda: provider.get_asset_metadata(normalized)
        )

    history = await provider_request(
        "TIME_SERIES_DAILY",
        lambda: provider.get_historical_bars(normalized, start, end, timeframe),
    )
    bars_by_key = {
        (bar.timeframe.value, bar.event_time, bar.provider): bar for bar in history.bars
    }
    latest = await provider_request(
        "GLOBAL_QUOTE", lambda: provider.get_latest_bar(normalized)
    )
    if latest is not None and start <= latest.event_time.date() <= end:
        bars_by_key[(latest.timeframe.value, latest.event_time, latest.provider)] = latest
    if asset is None and metadata is not None:
        asset = repository.upsert_asset(metadata)
    if asset is None:
        raise RuntimeError("Provider metadata did not create an asset")
    stats = repository.upsert_bars(asset.id, list(bars_by_key.values()))
    session.commit()
    return SyncResult(
        symbol=normalized,
        provider=provider.name,
        inserted=stats.inserted,
        updated=stats.updated,
        rejected=history.rejected_count,
        received_at=utc_now(),
    )
