from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models import Asset, MarketBar
from app.modules.data_sources.contracts import ProviderAssetMetadata, ProviderMarketBar, Timeframe


@dataclass(frozen=True, slots=True)
class UpsertStats:
    inserted: int = 0
    updated: int = 0


class MarketDataRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_asset(self, symbol: str) -> Asset | None:
        return self.session.scalar(select(Asset).where(Asset.symbol == symbol.upper()))

    def list_assets(self) -> list[Asset]:
        return list(self.session.scalars(select(Asset).where(Asset.is_active.is_(True)).order_by(Asset.symbol)))

    def upsert_asset(self, metadata: ProviderAssetMetadata) -> Asset:
        asset = self.get_asset(metadata.symbol)
        values = {
            "name": metadata.name,
            "asset_type": metadata.asset_type,
            "exchange": metadata.exchange,
            "sector": metadata.sector,
            "industry": metadata.industry,
            "currency": metadata.currency,
            "provider_symbol": metadata.provider_symbol,
            "is_active": True,
        }
        if asset is None:
            asset = Asset(symbol=metadata.symbol, **values)
            self.session.add(asset)
        else:
            for key, value in values.items():
                setattr(asset, key, value)
            asset.updated_at = utc_now()
        self.session.flush()
        return asset

    def history(
        self,
        asset_id: int,
        start: datetime,
        end: datetime,
        timeframe: Timeframe,
        provider: str,
    ) -> list[MarketBar]:
        statement: Select[tuple[MarketBar]] = (
            select(MarketBar)
            .where(
                MarketBar.asset_id == asset_id,
                MarketBar.timeframe == timeframe.value,
                MarketBar.event_time >= start,
                MarketBar.event_time <= end,
                MarketBar.provider == provider,
            )
            .order_by(MarketBar.event_time)
        )
        return list(self.session.scalars(statement))

    def latest(
        self,
        asset_id: int,
        provider: str,
        timeframe: Timeframe = Timeframe.DAY_1,
    ) -> MarketBar | None:
        return self.session.scalar(
            select(MarketBar)
            .where(
                MarketBar.asset_id == asset_id,
                MarketBar.timeframe == timeframe.value,
                MarketBar.provider == provider,
                MarketBar.close.is_not(None),
            )
            .order_by(MarketBar.event_time.desc(), MarketBar.received_at.desc())
            .limit(1)
        )

    def latest_at_or_before(
        self,
        asset_id: int,
        provider: str,
        as_of: datetime,
        timeframe: Timeframe = Timeframe.DAY_1,
    ) -> MarketBar | None:
        return self.session.scalar(
            select(MarketBar)
            .where(
                MarketBar.asset_id == asset_id,
                MarketBar.timeframe == timeframe.value,
                MarketBar.provider == provider,
                MarketBar.close.is_not(None),
                MarketBar.event_time <= as_of,
                MarketBar.received_at <= as_of,
            )
            .order_by(MarketBar.event_time.desc(), MarketBar.received_at.desc())
            .limit(1)
        )

    def latest_two(
        self,
        asset_id: int,
        provider: str,
        timeframe: Timeframe = Timeframe.DAY_1,
    ) -> list[MarketBar]:
        latest = self.latest(asset_id, provider, timeframe)
        if latest is None:
            return []
        previous = self.session.scalar(
            select(MarketBar)
            .where(
                MarketBar.asset_id == asset_id,
                MarketBar.timeframe == timeframe.value,
                MarketBar.provider == latest.provider,
                MarketBar.close.is_not(None),
                MarketBar.event_time < latest.event_time,
            )
            .order_by(MarketBar.event_time.desc(), MarketBar.received_at.desc())
            .limit(1)
        )
        return [latest, previous] if previous is not None else [latest]

    def count_bars(self, provider: str) -> int:
        return int(self.session.scalar(
            select(func.count()).select_from(MarketBar).where(MarketBar.provider == provider)
        ) or 0)

    def delete_demo_bars(self) -> int:
        count = self.count_bars("demo")
        if count:
            self.session.execute(delete(MarketBar).where(MarketBar.provider == "demo"))
            self.session.flush()
        return count

    def upsert_bars(self, asset_id: int, bars: list[ProviderMarketBar]) -> UpsertStats:
        inserted = 0
        updated = 0
        comparable = (
            "open", "high", "low", "close", "adjusted_close", "volume", "published_at"
        )
        for bar in bars:
            existing = self.session.scalar(
                select(MarketBar).where(
                    MarketBar.asset_id == asset_id,
                    MarketBar.timeframe == bar.timeframe.value,
                    MarketBar.event_time == bar.event_time,
                    MarketBar.provider == bar.provider,
                )
            )
            if existing is None:
                self.session.add(MarketBar(
                    asset_id=asset_id, timeframe=bar.timeframe.value,
                    event_time=bar.event_time, open=bar.open, high=bar.high, low=bar.low,
                    close=bar.close, adjusted_close=bar.adjusted_close, volume=bar.volume,
                    provider=bar.provider, published_at=bar.published_at,
                    received_at=bar.received_at,
                ))
                self.session.flush()
                inserted += 1
                continue
            if any(getattr(existing, field) != getattr(bar, field) for field in comparable):
                for field in comparable:
                    setattr(existing, field, getattr(bar, field))
                existing.received_at = bar.received_at
                updated += 1
        self.session.flush()
        return UpsertStats(inserted=inserted, updated=updated)
