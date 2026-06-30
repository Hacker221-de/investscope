from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MarketBar
from app.modules.data_sources import ProviderAssetMetadata, ProviderMarketBar, Timeframe
from app.repositories import MarketDataRepository


def test_duplicate_protection_and_idempotent_upsert(db_session: Session) -> None:
    repository = MarketDataRepository(db_session)
    asset = repository.upsert_asset(ProviderAssetMetadata(
        symbol="AAPL", name="Apple Inc.", asset_type="Equity", exchange="NASDAQ",
        sector="Technology", industry="Consumer Electronics", currency="USD",
        provider_symbol="AAPL",
    ))
    market_bar = ProviderMarketBar(
        timeframe=Timeframe.DAY_1,
        event_time=datetime(2026, 6, 27, tzinfo=UTC),
        open=Decimal("200"), high=Decimal("210"), low=Decimal("198"),
        close=Decimal("208"), volume=100, provider="test",
        published_at=datetime(2026, 6, 27, 23, tzinfo=UTC),
        received_at=datetime(2026, 6, 28, tzinfo=UTC),
    )

    first = repository.upsert_bars(asset.id, [market_bar])
    second = repository.upsert_bars(asset.id, [market_bar])
    db_session.commit()

    assert first.inserted == 1
    assert second.inserted == 0
    assert second.updated == 0
    assert db_session.scalar(select(func.count()).select_from(MarketBar)) == 1
