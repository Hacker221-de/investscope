import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.models import ProviderRequestLog
from app.modules.data_sources import (
    AlphaVantageMarketDataProvider,
    ProviderAssetMetadata,
    Timeframe,
)
from app.modules.data_sources.gateway import AlphaVantageRequestGateway
from app.modules.data_sources.limits import ProviderRequestCoordinator
from app.modules.data_sources.sync import synchronize_market_data
from app.repositories import MarketDataRepository


def settings() -> Settings:
    return Settings(
        alpha_vantage_daily_limit=25,
        alpha_vantage_daily_reserve=1,
        alpha_vantage_min_interval_seconds=1.5,
    )


def payload(request: httpx.Request, day: str) -> httpx.Response:
    function = request.url.params["function"]
    if function == "TIME_SERIES_DAILY":
        return httpx.Response(200, json={"Time Series (Daily)": {day: {
            "1. open": "100", "2. high": "106", "3. low": "99",
            "4. close": "104", "5. volume": "1000",
        }}})
    if function == "GLOBAL_QUOTE":
        return httpx.Response(200, json={"Global Quote": {
            "02. open": "100", "03. high": "107", "04. low": "99",
            "05. price": "105", "06. volume": "1100", "07. latest trading day": day,
        }})
    raise AssertionError(f"Unexpected Alpha Vantage function: {function}")


def seed_asset(session: Session, symbol: str) -> None:
    MarketDataRepository(session).upsert_asset(ProviderAssetMetadata(
        symbol=symbol, name=symbol, asset_type="Equity", currency="USD",
        provider_symbol=symbol,
    ))
    session.commit()


def test_one_sync_spaces_daily_and_quote_requests_with_monotonic_clock(
    db_session: Session,
) -> None:
    seed_asset(db_session, "AAPL")
    wall = [datetime(2026, 7, 1, 12, tzinfo=UTC)]
    mono = [0.0]
    calls: list[tuple[str, float]] = []

    async def fake_sleep(seconds: float) -> None:
        wall[0] += timedelta(seconds=seconds)
        mono[0] += seconds
        await asyncio.sleep(0)

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.params["function"], mono[0]))
        await asyncio.sleep(0)
        return payload(request, "2026-07-01")

    async def run() -> None:
        coordinator = ProviderRequestCoordinator(
            db_session, settings(), now=lambda: wall[0],
            monotonic=lambda: mono[0], sleep=fake_sleep,
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = AlphaVantageRequestGateway(
                api_key="test-key", base_url="https://example.test", timeout_seconds=1,
                coordinator=coordinator, client=client,
            )
            provider = AlphaVantageMarketDataProvider(gateway)
            result = await synchronize_market_data(
                db_session, provider, "AAPL", date(2026, 7, 1), date(2026, 7, 1),
                Timeframe.DAY_1, coordinator,
            )
            assert result.inserted == 1

    asyncio.run(run())

    assert [name for name, _ in calls] == ["TIME_SERIES_DAILY", "GLOBAL_QUOTE"]
    assert calls[1][1] - calls[0][1] >= 1.5
    logs = list(db_session.scalars(select(ProviderRequestLog).order_by(ProviderRequestLog.id)))
    assert [entry.status_code for entry in logs] == [200, 200]
    assert all(entry.successful for entry in logs)
    assert all(entry.started_at <= entry.completed_at for entry in logs)


def test_parallel_syncs_share_lock_and_preserve_interval(db_session: Session) -> None:
    seed_asset(db_session, "AAPL")
    seed_asset(db_session, "MSFT")
    engine = db_session.get_bind()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    wall = [datetime(2026, 7, 1, 12, tzinfo=UTC)]
    mono = [0.0]
    starts: list[float] = []
    active = 0
    max_active = 0

    async def fake_sleep(seconds: float) -> None:
        wall[0] += timedelta(seconds=seconds)
        mono[0] += seconds
        await asyncio.sleep(0)

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        starts.append(mono[0])
        await asyncio.sleep(0)
        active -= 1
        return payload(request, "2026-07-01")

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            async def sync_symbol(symbol: str, session: Session) -> None:
                coordinator = ProviderRequestCoordinator(
                    session, settings(), now=lambda: wall[0],
                    monotonic=lambda: mono[0], sleep=fake_sleep,
                )
                gateway = AlphaVantageRequestGateway(
                    api_key="test-key", base_url="https://example.test", timeout_seconds=1,
                    coordinator=coordinator, client=client,
                )
                provider = AlphaVantageMarketDataProvider(gateway)
                await synchronize_market_data(
                    session, provider, symbol, date(2026, 7, 1), date(2026, 7, 1),
                    Timeframe.DAY_1, coordinator,
                )

            with factory() as first, factory() as second:
                await asyncio.gather(
                    sync_symbol("AAPL", first),
                    sync_symbol("MSFT", second),
                )

    asyncio.run(run())

    assert len(starts) == 4
    assert max_active == 1
    assert all(later - earlier >= 1.5 for earlier, later in zip(starts, starts[1:]))
