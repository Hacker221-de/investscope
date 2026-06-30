from datetime import date
import asyncio

import httpx
import pytest

from app.modules.data_sources import (
    AlphaVantageMarketDataProvider,
    ProviderTimeoutError,
    Timeframe,
)


def test_mocked_alpha_vantage_responses_are_parsed_without_zero_filling() -> None:
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
            provider = AlphaVantageMarketDataProvider("key", "https://example.test", client=client)
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


def test_alpha_vantage_timeout_is_mapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = AlphaVantageMarketDataProvider("key", "https://example.test", client=client)
            await provider.get_asset_metadata("AAPL")

    with pytest.raises(ProviderTimeoutError):
        asyncio.run(run())
