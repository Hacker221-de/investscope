from datetime import date
import asyncio

import httpx
import pytest

from app.modules.data_sources import (
    AlphaVantageMarketDataProvider,
    ProviderBurstLimitError,
    ProviderInvalidRequestError,
    ProviderTimeoutError,
    Timeframe,
)
from app.core.config import Settings
from app.modules.data_sources.gateway import AlphaVantageRequestGateway
from app.modules.data_sources.limits import ProviderRequestCoordinator
from sqlalchemy.orm import Session


def alpha_provider(
    client: httpx.AsyncClient,
    db_session: Session,
) -> AlphaVantageMarketDataProvider:
    settings = Settings(
        alpha_vantage_daily_limit=25,
        alpha_vantage_daily_reserve=1,
        alpha_vantage_min_interval_seconds=0,
    )
    coordinator = ProviderRequestCoordinator(db_session, settings)
    gateway = AlphaVantageRequestGateway(
        api_key="key",
        base_url="https://example.test",
        timeout_seconds=1,
        coordinator=coordinator,
        client=client,
    )
    return AlphaVantageMarketDataProvider(gateway)


def test_mocked_alpha_vantage_responses_are_parsed_without_zero_filling(
    db_session: Session,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        function = request.url.params["function"]
        if function == "SYMBOL_SEARCH":
            return httpx.Response(200, json={"bestMatches": [{
                "1. symbol": "AAPL", "2. name": "Apple Inc.", "3. type": "Equity",
                "4. region": "United States", "8. currency": "USD",
            }]})
        return httpx.Response(200, json={"Time Series (Daily)": {
            "2026-06-29": {
                "1. open": "200.10", "2. high": "205.20", "3. low": "199.00",
                "4. close": "204.00", "5. volume": "12345",
            },
            "2026-06-28": {"1. open": "bad", "4. close": "201"},
        }})

    async def run() -> tuple[object, object]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = alpha_provider(client, db_session)
            metadata = await provider.get_asset_metadata("aapl")
            result = await provider.get_historical_bars(
                "AAPL", date(2026, 6, 1), date(2026, 6, 30), Timeframe.DAY_1,
            )
            return metadata, result

    metadata, result = asyncio.run(run())

    assert metadata.symbol == "AAPL"
    assert len(result.bars) == 1
    assert result.bars[0].adjusted_close is None
    assert result.rejected_count == 1


def test_alpha_vantage_timeout_is_mapped(db_session: Session) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = alpha_provider(client, db_session)
            await provider.get_asset_metadata("AAPL")

    with pytest.raises(ProviderTimeoutError):
        asyncio.run(run())


def test_alpha_vantage_429_is_not_retried_and_preserves_retry_after(
    db_session: Session,
) -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(429, headers={"Retry-After": "12"}, request=request)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = alpha_provider(client, db_session)
            await provider.get_latest_bar("AAPL")

    with pytest.raises(ProviderBurstLimitError) as captured:
        asyncio.run(run())

    assert captured.value.retry_after_seconds == 12
    assert requests == 1


def test_daily_request_contains_only_supported_external_query_params(
    db_session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        return httpx.Response(200, json={"Time Series (Daily)": {
            "2026-06-29": {
                "1. open": "100", "2. high": "102", "3. low": "99",
                "4. close": "101", "5. volume": "1000",
            },
        }})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = alpha_provider(client, db_session)
            await provider.get_historical_bars(
                "AAPL", date(2026, 1, 1), date(2026, 6, 30), Timeframe.DAY_1,
            )

    caplog.set_level("INFO", logger="app.modules.data_sources.gateway")
    asyncio.run(run())

    assert captured == {
        "function": "TIME_SERIES_DAILY",
        "symbol": "AAPL",
        "outputsize": "compact",
        "datatype": "json",
        "apikey": "key",
    }
    assert not {"timeframe", "start", "end", "provider", "request_group_id", "min_interval_seconds"} & captured.keys()
    assert "function=TIME_SERIES_DAILY" in caplog.text
    assert "symbol=AAPL" in caplog.text
    assert "apikey" not in caplog.text.lower()
    assert "key" not in caplog.text


def test_alpha_error_message_becomes_provider_invalid_request(
    db_session: Session,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "Error Message": "Invalid API call. Please retry or visit the documentation",
        })

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = alpha_provider(client, db_session)
            await provider.get_historical_bars(
                "AAPL", date(2026, 1, 1), date(2026, 6, 30), Timeframe.DAY_1,
            )

    with pytest.raises(ProviderInvalidRequestError):
        asyncio.run(run())
