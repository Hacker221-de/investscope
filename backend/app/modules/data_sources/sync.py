from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.modules.data_sources.contracts import MarketDataProvider, Timeframe
from app.repositories import MarketDataRepository


@dataclass(frozen=True, slots=True)
class SyncResult:
    symbol: str
    provider: str
    inserted: int
    updated: int
    rejected: int


async def synchronize_market_data(
    session: Session,
    provider: MarketDataProvider,
    symbol: str,
    start: date,
    end: date,
    timeframe: Timeframe,
) -> SyncResult:
    repository = MarketDataRepository(session)
    normalized = symbol.upper()
    asset = repository.get_asset(normalized)
    if asset is None:
        metadata = await provider.get_asset_metadata(normalized)
        asset = repository.upsert_asset(metadata)

    history = await provider.get_historical_bars(normalized, start, end, timeframe)
    bars_by_key = {
        (bar.timeframe.value, bar.event_time, bar.provider): bar for bar in history.bars
    }
    latest = await provider.get_latest_bar(normalized)
    if latest is not None and start <= latest.event_time.date() <= end:
        bars_by_key[(latest.timeframe.value, latest.event_time, latest.provider)] = latest
    stats = repository.upsert_bars(asset.id, list(bars_by_key.values()))
    session.commit()
    return SyncResult(
        symbol=normalized,
        provider=provider.name,
        inserted=stats.inserted,
        updated=stats.updated,
        rejected=history.rejected_count,
    )
