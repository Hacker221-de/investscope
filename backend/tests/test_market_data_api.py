from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.market_data import get_market_data_provider
from app.core.config import Settings, get_settings
from app.core.time import utc_now
from app.main import app
from app.modules.data_sources import (
    DemoMarketDataProvider,
    ProviderAssetMetadata,
    ProviderMarketBar,
    ProviderTimeoutError,
    Timeframe,
)
from app.repositories import MarketDataRepository


def _use_alpha_vantage_as_default() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        market_data_provider="alpha_vantage",
        alpha_vantage_api_key="test-key",
    )


def _seed_mixed_provider_bars(db_session: Session) -> None:
    repository = MarketDataRepository(db_session)
    asset = repository.upsert_asset(ProviderAssetMetadata(
        symbol="MIXED", name="Mixed providers", asset_type="Equity", currency="USD",
        provider_symbol="MIXED",
    ))
    repository.upsert_bars(asset.id, [
        ProviderMarketBar(
            timeframe=Timeframe.DAY_1,
            event_time=datetime(2026, 6, 26, tzinfo=UTC),
            close=Decimal("100"), provider="alpha_vantage",
            received_at=datetime(2026, 6, 26, 23, tzinfo=UTC),
        ),
        ProviderMarketBar(
            timeframe=Timeframe.DAY_1,
            event_time=datetime(2026, 6, 27, tzinfo=UTC),
            close=Decimal("105"), provider="alpha_vantage",
            received_at=datetime(2026, 6, 27, 23, tzinfo=UTC),
        ),
        ProviderMarketBar(
            timeframe=Timeframe.DAY_1,
            event_time=datetime(2026, 6, 29, tzinfo=UTC),
            close=Decimal("999"), provider="demo",
            received_at=datetime(2026, 6, 29, 23, tzinfo=UTC),
        ),
    ])
    db_session.commit()


def test_market_sync_is_idempotent_and_exposes_all_read_endpoints(
    market_client: TestClient,
) -> None:
    path = "/api/market/AAPL/sync?start=2026-06-01&end=2026-06-10"
    first = market_client.post(path)
    second = market_client.post(path)

    assert first.status_code == 200
    assert first.json()["inserted"] > 0
    assert first.json()["rejected"] == 0
    assert second.json()["inserted"] == 0
    assert second.json()["updated"] == 0
    assert market_client.get("/api/assets").json()[0]["symbol"] == "AAPL"
    assert market_client.get("/api/assets/AAPL").status_code == 200
    assert market_client.get(
        "/api/market/AAPL/history?start=2026-06-01&end=2026-06-10"
    ).json()["bars"]
    assert market_client.get("/api/market/AAPL/latest").status_code == 200


def test_invalid_ticker_and_future_range_are_rejected(market_client: TestClient) -> None:
    assert market_client.post("/api/market/BAD$/sync").status_code == 422
    future = date.today() + timedelta(days=30)
    response = market_client.post(f"/api/market/AAPL/sync?end={future.isoformat()}")
    assert response.status_code == 422


def test_missing_quote_returns_clear_404(market_client: TestClient, db_session: Session) -> None:
    MarketDataRepository(db_session).upsert_asset(ProviderAssetMetadata(
        symbol="EMPTY", name="No quote", asset_type="Equity", currency="USD",
        provider_symbol="EMPTY",
    ))
    db_session.commit()

    response = market_client.get("/api/market/EMPTY/latest")

    assert response.status_code == 404
    assert response.json()["detail"] == "No saved quote is available"


def test_old_quote_is_marked_stale(market_client: TestClient, db_session: Session) -> None:
    repository = MarketDataRepository(db_session)
    asset = repository.upsert_asset(ProviderAssetMetadata(
        symbol="OLD", name="Old quote", asset_type="Equity", currency="USD",
        provider_symbol="OLD",
    ))
    old = utc_now() - timedelta(days=5)
    repository.upsert_bars(asset.id, [ProviderMarketBar(
        timeframe=Timeframe.DAY_1, event_time=old.replace(hour=0, minute=0, second=0),
        close=Decimal("10"), provider="demo", published_at=old,
        received_at=old + timedelta(minutes=1),
    )])
    db_session.commit()

    assert market_client.get("/api/market/OLD/latest").json()["quote"]["is_stale"] is True


def test_newer_demo_bar_does_not_override_configured_alpha_vantage(
    market_client: TestClient,
    db_session: Session,
) -> None:
    _seed_mixed_provider_bars(db_session)
    _use_alpha_vantage_as_default()

    response = market_client.get("/api/market/MIXED/latest")

    assert response.status_code == 200
    assert response.json()["quote"]["source"] == "alpha_vantage"
    assert response.json()["quote"]["close"] == "105.00000000"
    assert response.json()["quote"]["previous_close"] == "100.00000000"
    assert market_client.get("/api/assets/MIXED").json()["latest_quote"]["source"] == "alpha_vantage"


def test_history_does_not_mix_providers(
    market_client: TestClient,
    db_session: Session,
) -> None:
    _seed_mixed_provider_bars(db_session)
    _use_alpha_vantage_as_default()

    response = market_client.get(
        "/api/market/MIXED/history?start=2026-06-01&end=2026-06-30"
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "alpha_vantage"
    assert len(response.json()["bars"]) == 2
    assert {bar["provider"] for bar in response.json()["bars"]} == {"alpha_vantage"}


def test_explicit_demo_provider_override_works(
    market_client: TestClient,
    db_session: Session,
) -> None:
    _seed_mixed_provider_bars(db_session)
    _use_alpha_vantage_as_default()

    latest = market_client.get("/api/market/MIXED/latest?provider=demo")
    history = market_client.get(
        "/api/market/MIXED/history?start=2026-06-01&end=2026-06-30&provider=demo"
    )

    assert latest.status_code == 200
    assert latest.json()["quote"]["source"] == "demo"
    assert latest.json()["quote"]["close"] == "999.00000000"
    assert history.json()["provider"] == "demo"
    assert len(history.json()["bars"]) == 1


class TimeoutProvider(DemoMarketDataProvider):
    async def get_asset_metadata(self, symbol: str) -> ProviderAssetMetadata:
        raise ProviderTimeoutError("provider timed out")


def test_provider_timeout_becomes_gateway_timeout(market_client: TestClient) -> None:
    app.dependency_overrides[get_market_data_provider] = lambda: TimeoutProvider()

    response = market_client.post("/api/market/AAPL/sync?start=2026-06-01&end=2026-06-02")

    assert response.status_code == 504
