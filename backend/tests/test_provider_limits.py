import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.market_data import get_market_data_provider
from app.core.config import Settings, get_settings
from app.core.time import utc_now
from app.main import app
from app.models import ProviderRequestLog
from app.modules.data_sources import (
    HistoricalBarsResult,
    MarketDataProvider,
    ProviderAssetMetadata,
    ProviderBurstLimitError,
    ProviderInvalidRequestError,
    ProviderMarketBar,
    Timeframe,
)
from app.modules.data_sources.limits import ProviderRequestCoordinator
from app.repositories import MarketDataRepository, ProviderRequestRepository


class CountingAlphaProvider(MarketDataProvider):
    name = "alpha_vantage"

    def __init__(self, *, fail_history: bool = False, fail_latest: bool = False) -> None:
        self.calls: list[str] = []
        self.fail_history = fail_history
        self.fail_latest = fail_latest

    async def get_asset_metadata(self, symbol: str) -> ProviderAssetMetadata:
        self.calls.append("metadata")
        return ProviderAssetMetadata(
            symbol=symbol, name=symbol, asset_type="Equity", currency="USD",
            provider_symbol=symbol,
        )

    async def get_historical_bars(
        self, symbol: str, start: date, end: date, timeframe: Timeframe
    ) -> HistoricalBarsResult:
        self.calls.append("history")
        if self.fail_history:
            raise ProviderBurstLimitError("rate limited", retry_after_seconds=10)
        now = utc_now()
        return HistoricalBarsResult(bars=[ProviderMarketBar(
            timeframe=timeframe,
            event_time=datetime(now.year, now.month, now.day, tzinfo=UTC),
            open=Decimal("100"), high=Decimal("105"), low=Decimal("99"),
            close=Decimal("104"), volume=100, provider=self.name,
            published_at=now, received_at=now,
        )])

    async def get_latest_bar(self, symbol: str) -> ProviderMarketBar | None:
        self.calls.append("latest")
        if self.fail_latest:
            raise ProviderBurstLimitError("rate limited", retry_after_seconds=10)
        now = utc_now()
        return ProviderMarketBar(
            timeframe=Timeframe.DAY_1,
            event_time=datetime(now.year, now.month, now.day, tzinfo=UTC),
            open=Decimal("100"), high=Decimal("106"), low=Decimal("99"),
            close=Decimal("105"), volume=110, provider=self.name,
            published_at=now, received_at=now,
        )


def _settings(**changes: object) -> Settings:
    values: dict[str, object] = {
        "market_data_provider": "alpha_vantage",
        "alpha_vantage_api_key": "test-secret-key",
        "alpha_vantage_daily_limit": 25,
        "alpha_vantage_daily_reserve": 1,
        "alpha_vantage_min_interval_seconds": 0,
        "alpha_vantage_rate_limit_cooldown_seconds": 60,
        "market_data_stale_after_hours": 36,
    }
    values.update(changes)
    return Settings.model_validate(values)


def _configure(provider: CountingAlphaProvider, settings: Settings) -> None:
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_market_data_provider] = lambda: provider


def _seed_quote(db_session: Session, *, fresh: bool) -> None:
    now = utc_now()
    reference = now - (timedelta(hours=1) if fresh else timedelta(days=3))
    repository = MarketDataRepository(db_session)
    asset = repository.upsert_asset(ProviderAssetMetadata(
        symbol="AAPL", name="Apple Inc.", asset_type="Equity", currency="USD",
        provider_symbol="AAPL",
    ))
    repository.upsert_bars(asset.id, [ProviderMarketBar(
        timeframe=Timeframe.DAY_1,
        event_time=datetime(reference.year, reference.month, reference.day, tzinfo=UTC),
        close=Decimal("100"), provider="alpha_vantage",
        published_at=reference, received_at=reference,
    )])
    db_session.commit()


def _add_request_logs(db_session: Session, count: int) -> None:
    repository = ProviderRequestRepository(db_session)
    now = utc_now()
    for index in range(count):
        repository.add(
            provider="alpha_vantage", endpoint="GLOBAL_QUOTE", symbol="AAPL",
            requested_at=now - timedelta(minutes=index),
            started_at=now - timedelta(minutes=index),
            completed_at=now - timedelta(minutes=index),
            status_code=200, retry_after_seconds=None,
            successful=True, error_type=None, request_group_id=str(uuid4()),
        )
    db_session.commit()


def test_fresh_data_prevents_external_request(
    market_client: TestClient, db_session: Session,
) -> None:
    provider = CountingAlphaProvider()
    _seed_quote(db_session, fresh=True)
    _configure(provider, _settings())

    response = market_client.post("/api/market/AAPL/sync")

    assert response.status_code == 200
    assert response.json()["skipped"] is True
    assert response.json()["reason"] == "fresh_data"
    assert response.json()["skip_reason"] == "fresh_data"
    assert response.json()["latest_event_time"] is not None
    assert response.json()["latest_received_at"] is not None
    assert provider.calls == []
    assert response.json()["requests_used_today"] == 0


def test_stale_data_allows_requests_and_next_sync_is_free(
    market_client: TestClient, db_session: Session,
) -> None:
    provider = CountingAlphaProvider()
    _seed_quote(db_session, fresh=False)
    _configure(provider, _settings())

    first = market_client.post("/api/market/AAPL/sync")
    second = market_client.post("/api/market/AAPL/sync")

    assert first.status_code == 200
    assert first.json()["skipped"] is False
    assert first.json()["requests_used_today"] == 2
    assert provider.calls == ["history", "latest"]
    assert second.status_code == 200
    assert second.json()["skipped"] is True
    assert second.json()["requests_used_today"] == 2
    assert provider.calls == ["history", "latest"]


def test_daily_limit_with_reserve_blocks_before_request(
    market_client: TestClient, db_session: Session,
) -> None:
    provider = CountingAlphaProvider()
    _seed_quote(db_session, fresh=False)
    _add_request_logs(db_session, 24)
    _configure(provider, _settings())

    response = market_client.post("/api/market/AAPL/sync")

    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "provider_daily_limit"
    assert response.json()["detail"]["message"] == "Действует временное ограничение частоты запросов"
    assert response.json()["detail"]["requests_used_today"] == 24
    assert response.json()["detail"]["daily_limit"] == 25
    assert provider.calls == []


def test_provider_429_is_logged_and_mapped_to_safe_response(
    market_client: TestClient, db_session: Session,
) -> None:
    provider = CountingAlphaProvider(fail_history=True)
    _seed_quote(db_session, fresh=False)
    _configure(provider, _settings())

    response = market_client.post("/api/market/AAPL/sync")
    repeated = market_client.post("/api/market/AAPL/sync")

    assert response.status_code == 429
    detail = response.json()["detail"]
    assert detail == {
        "code": "provider_burst_limit",
        "provider": "alpha_vantage",
        "message": "Действует временное ограничение частоты запросов",
        "retry_after_seconds": 10,
        "requests_used_today": 1,
        "daily_limit": 25,
    }
    log = db_session.scalar(select(ProviderRequestLog))
    assert log is not None
    assert log.successful is False
    assert log.error_type == "provider_burst_limit"
    assert log.started_at is not None
    assert log.completed_at is not None
    assert log.retry_after_seconds == 10
    assert repeated.status_code == 429
    assert provider.calls == ["history"]
    assert db_session.scalar(select(func.count()).select_from(ProviderRequestLog)) == 1


def test_successful_and_failed_requests_share_group_and_are_counted(
    market_client: TestClient, db_session: Session,
) -> None:
    provider = CountingAlphaProvider(fail_latest=True)
    _seed_quote(db_session, fresh=False)
    _configure(provider, _settings())

    response = market_client.post("/api/market/AAPL/sync")
    logs = list(db_session.scalars(select(ProviderRequestLog).order_by(ProviderRequestLog.id)))

    assert response.status_code == 429
    assert len(logs) == 2
    assert [entry.successful for entry in logs] == [True, False]
    assert len({entry.request_group_id for entry in logs}) == 1
    assert db_session.scalar(select(func.count()).select_from(ProviderRequestLog)) == 2


def test_provider_status_never_exposes_api_key(
    market_client: TestClient,
) -> None:
    secret = "must-never-reach-frontend"
    settings = _settings(alpha_vantage_api_key=secret)
    _configure(CountingAlphaProvider(), settings)

    response = market_client.get("/api/providers/market-data/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured_provider"] == "alpha_vantage"
    assert payload["daily_limit"] == 25
    assert payload["remaining_requests"] == 25
    assert secret not in response.text
    assert "api_key" not in response.text


def test_alpha_requests_are_spaced_by_configured_monotonic_interval(
    db_session: Session,
) -> None:
    provider = CountingAlphaProvider()
    current = [datetime(2026, 6, 30, 12, tzinfo=UTC)]
    monotonic_time = [0.0]
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)
        current[0] += timedelta(seconds=seconds)
        monotonic_time[0] += seconds

    coordinator = ProviderRequestCoordinator(
        db_session,
        _settings(alpha_vantage_min_interval_seconds=1.5),
        now=lambda: current[0],
        monotonic=lambda: monotonic_time[0],
        sleep=fake_sleep,
    )

    async def run() -> None:
        await coordinator.request(
            provider=provider.name, endpoint="TIME_SERIES_DAILY", symbol="AAPL",
            request_group_id=str(uuid4()), operation=lambda: provider.get_latest_bar("AAPL"),
        )
        await coordinator.request(
            provider=provider.name, endpoint="GLOBAL_QUOTE", symbol="AAPL",
            request_group_id=str(uuid4()), operation=lambda: provider.get_latest_bar("AAPL"),
        )

    asyncio.run(run())

    assert waits == [1.5]


class InvalidRequestAlphaProvider(CountingAlphaProvider):
    async def get_historical_bars(
        self, symbol: str, start: date, end: date, timeframe: Timeframe
    ) -> HistoricalBarsResult:
        self.calls.append("history")
        raise ProviderInvalidRequestError("external provider rejected request")


def test_provider_invalid_request_is_http_502_not_asset_404(
    market_client: TestClient,
    db_session: Session,
) -> None:
    provider = InvalidRequestAlphaProvider()
    _seed_quote(db_session, fresh=False)
    _configure(provider, _settings())

    response = market_client.post("/api/market/AAPL/sync")

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "provider_invalid_request",
        "provider": "alpha_vantage",
        "message": "Провайдер отклонил параметры запроса",
    }
