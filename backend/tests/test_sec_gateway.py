import asyncio

import httpx
import pytest

from app.modules.fundamental_analysis.contracts import (
    SecAccessDeniedError,
    SecCompanyNotFoundError,
    SecInvalidResponseError,
    SecRateLimitError,
    SecTimeoutError,
)
from app.modules.fundamental_analysis.sec_gateway import SecEdgarRequestGateway, SecResponseCache


def _gateway(
    client: httpx.AsyncClient,
    **kwargs: object,
) -> SecEdgarRequestGateway:
    return SecEdgarRequestGateway(
        user_agent="InvestScope tests@example.com",
        max_requests_per_second=5,
        cache_ttl_hours=24,
        timeout_seconds=1,
        client=client,
        cache=SecResponseCache(),
        **kwargs,
    )


def test_sec_user_agent_is_required() -> None:
    with pytest.raises(ValueError, match="User-Agent"):
        SecEdgarRequestGateway(
            user_agent="", max_requests_per_second=5,
            cache_ttl_hours=24, timeout_seconds=1,
        )


def test_sec_gateway_sends_required_headers_and_uses_official_urls() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = _gateway(client)
            await gateway.get_submissions("0000320193")
            await gateway.get_company_facts("0000320193")

    asyncio.run(run())
    assert str(requests[0].url) == "https://data.sec.gov/submissions/CIK0000320193.json"
    assert str(requests[1].url) == (
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    )
    assert all(request.headers["user-agent"] == "InvestScope tests@example.com" for request in requests)
    assert all("gzip" in request.headers["accept-encoding"] for request in requests)


def test_sec_gateway_rate_limits_each_request_without_real_sleep() -> None:
    monotonic = [0.0]
    calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        monotonic[0] += seconds
        await asyncio.sleep(0)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(monotonic[0])
        return httpx.Response(200, json={})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = _gateway(
                client, monotonic=lambda: monotonic[0], sleep=fake_sleep
            )
            await gateway.get_submissions("0000320193")
            await gateway.get_company_facts("0000320193")

    asyncio.run(run())
    assert calls == [0.0, pytest.approx(0.2)]


def test_sec_limiter_is_shared_between_www_and_data_domains() -> None:
    monotonic = [0.0]
    calls: list[tuple[str, float]] = []

    async def fake_sleep(seconds: float) -> None:
        monotonic[0] += seconds
        await asyncio.sleep(0)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.host or "", monotonic[0]))
        return httpx.Response(200, json={})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = SecEdgarRequestGateway(
                user_agent="InvestScope tests@example.com",
                max_requests_per_second=1,
                cache_ttl_hours=24,
                timeout_seconds=1,
                client=client,
                cache=SecResponseCache(),
                monotonic=lambda: monotonic[0],
                sleep=fake_sleep,
            )
            await gateway.get_ticker_index()
            await gateway.get_submissions("0000320193")

    asyncio.run(run())
    assert [host for host, _ in calls] == ["www.sec.gov", "data.sec.gov"]
    assert calls[1][1] - calls[0][1] >= 1.0


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (403, SecAccessDeniedError),
        (404, SecCompanyNotFoundError),
        (429, SecRateLimitError),
    ],
)
def test_sec_gateway_maps_http_errors(status_code: int, error_type: type[Exception]) -> None:
    async def run() -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(status_code, json={}))
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(error_type):
                await _gateway(client).get_ticker_index()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("body", "error_type"),
    [
        ("<html>Request Rate Threshold Exceeded</html>", SecRateLimitError),
        ("The rate threshold has been exceeded", SecRateLimitError),
        ("Blocked due to excessive requests", SecRateLimitError),
        ("Your Request Originates from an Undeclared Automated Tool", SecAccessDeniedError),
        (
            "Undeclared Automated Tool; generic rate threshold policy text",
            SecAccessDeniedError,
        ),
    ],
)
def test_sec_gateway_classifies_403_html(body: str, error_type: type[Exception]) -> None:
    async def run() -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(403, text=body)
        )
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(error_type):
                await _gateway(client).get_ticker_index()

    asyncio.run(run())


def test_sec_gateway_maps_timeout_and_malformed_json() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret upstream detail", request=request)

    async def timeout_run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
            with pytest.raises(SecTimeoutError):
                await _gateway(client).get_ticker_index()

    async def malformed_run() -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"{"))
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(SecInvalidResponseError):
                await _gateway(client).get_ticker_index()

    asyncio.run(timeout_run())
    asyncio.run(malformed_run())


def test_sec_gateway_caches_responses() -> None:
    count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        return httpx.Response(200, json={"facts": {}})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = _gateway(client)
            await gateway.get_company_facts("0000320193")
            await gateway.get_company_facts("0000320193")

    asyncio.run(run())
    assert count == 1
