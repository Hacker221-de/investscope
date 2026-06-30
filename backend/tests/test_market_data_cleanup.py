from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.commands.market_data import purge_demo_market_bars
from app.models import Asset, MarketBar, Portfolio, Position
from app.modules.data_sources import ProviderAssetMetadata, ProviderMarketBar, Timeframe
from app.repositories import MarketDataRepository


def test_cleanup_deletes_only_demo_market_bars(db_session: Session) -> None:
    repository = MarketDataRepository(db_session)
    asset = repository.upsert_asset(ProviderAssetMetadata(
        symbol="AAPL", name="Apple Inc.", asset_type="Equity", currency="USD",
        provider_symbol="AAPL",
    ))
    repository.upsert_bars(asset.id, [
        ProviderMarketBar(
            timeframe=Timeframe.DAY_1,
            event_time=datetime(2026, 6, 29, tzinfo=UTC),
            close=Decimal("200"), provider="demo",
            received_at=datetime(2026, 6, 29, 23, tzinfo=UTC),
        ),
        ProviderMarketBar(
            timeframe=Timeframe.DAY_1,
            event_time=datetime(2026, 6, 28, tzinfo=UTC),
            close=Decimal("198"), provider="demo",
            received_at=datetime(2026, 6, 28, 23, tzinfo=UTC),
        ),
        ProviderMarketBar(
            timeframe=Timeframe.DAY_1,
            event_time=datetime(2026, 6, 27, tzinfo=UTC),
            close=Decimal("197"), provider="alpha_vantage",
            received_at=datetime(2026, 6, 27, 23, tzinfo=UTC),
        ),
    ])
    portfolio = Portfolio(name="Owned assets", base_currency="USD")
    db_session.add(portfolio)
    db_session.flush()
    db_session.add(Position(
        portfolio_id=portfolio.id, symbol="AAPL", quantity=Decimal("2"),
        average_purchase_price=Decimal("180"), purchase_date=date(2025, 1, 1),
        currency="USD", fees=None,
    ))
    db_session.commit()

    preview = purge_demo_market_bars(db_session)
    result = purge_demo_market_bars(db_session, confirmed=True)

    assert preview.found == 2
    assert preview.deleted == 0
    assert result.deleted == 2
    assert db_session.scalar(select(func.count()).select_from(MarketBar)) == 1
    assert db_session.scalar(select(MarketBar.provider)) == "alpha_vantage"
    assert db_session.scalar(select(func.count()).select_from(Asset)) == 1
    assert db_session.scalar(select(func.count()).select_from(Position)) == 1
