import logging
from typing import Any

import httpx

from app.modules.data_sources.contracts import (
    MarketDataProviderError,
    ProviderBurstLimitError,
    ProviderConfigurationError,
    ProviderInvalidRequestError,
    ProviderTimeoutError,
)
from app.modules.data_sources.limits import ProviderRequestCoordinator


logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


class AlphaVantageRequestGateway:
    """The only transport allowed to issue Alpha Vantage HTTP requests."""

    provider = "alpha_vantage"
    official_base_url = "https://www.alphavantage.co/query"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        coordinator: ProviderRequestCoordinator,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ProviderConfigurationError("Alpha Vantage API key is not configured")
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        if client is None and self.base_url != self.official_base_url:
            raise ProviderConfigurationError(
                f"Alpha Vantage base URL must be {self.official_base_url}"
            )
        self.timeout_seconds = timeout_seconds
        self.coordinator = coordinator
        self.client = client

    @staticmethod
    def _external_params(endpoint: str, params: dict[str, str]) -> dict[str, str]:
        if endpoint == "TIME_SERIES_DAILY":
            symbol = params.get("symbol")
            if not symbol:
                raise ProviderInvalidRequestError(
                    "TIME_SERIES_DAILY requires an external symbol"
                )
            return {
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol.upper(),
                "outputsize": "compact",
                "datatype": "json",
            }
        if endpoint == "GLOBAL_QUOTE":
            symbol = params.get("symbol")
            if not symbol:
                raise ProviderInvalidRequestError("GLOBAL_QUOTE requires an external symbol")
            return {"function": "GLOBAL_QUOTE", "symbol": symbol.upper()}
        if endpoint == "SYMBOL_SEARCH":
            keywords = params.get("keywords")
            if not keywords:
                raise ProviderInvalidRequestError("SYMBOL_SEARCH requires keywords")
            return {"function": "SYMBOL_SEARCH", "keywords": keywords}
        raise ProviderInvalidRequestError(f"Unsupported Alpha Vantage endpoint: {endpoint}")

    async def _send(self, params: dict[str, str]) -> dict[str, Any]:
        logger.info(
            "Alpha Vantage request function=%s symbol=%s outputsize=%s datatype=%s",
            params.get("function"),
            params.get("symbol"),
            params.get("outputsize"),
            params.get("datatype"),
        )
        request_params = {**params, "apikey": self._api_key}
        try:
            if self.client is not None:
                response = await self.client.get(self.base_url, params=request_params)
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.get(self.base_url, params=request_params)
        except httpx.TimeoutException:
            raise ProviderTimeoutError("Alpha Vantage request timed out") from None
        except httpx.HTTPError:
            raise MarketDataProviderError("Alpha Vantage request failed") from None

        if response.status_code == 429:
            retry_header = response.headers.get("Retry-After")
            retry_after = int(retry_header) if retry_header and retry_header.isdigit() else None
            raise ProviderBurstLimitError(
                "Alpha Vantage burst limit reached",
                retry_after_seconds=retry_after,
            )
        if response.status_code >= 400:
            raise MarketDataProviderError("Alpha Vantage request failed") from None
        try:
            payload = response.json()
        except ValueError:
            raise MarketDataProviderError("Alpha Vantage returned invalid JSON") from None
        if payload.get("Note") or payload.get("Information"):
            raise ProviderBurstLimitError("Alpha Vantage burst limit reached")
        if payload.get("Error Message"):
            raise ProviderInvalidRequestError(
                "Alpha Vantage rejected the request parameters"
            )
        return payload

    async def request(
        self,
        *,
        endpoint: str,
        symbol: str,
        request_group_id: str,
        params: dict[str, str],
    ) -> dict[str, Any]:
        external_params = self._external_params(endpoint, params)
        return await self.coordinator.request(
            provider=self.provider,
            endpoint=endpoint,
            symbol=symbol,
            request_group_id=request_group_id,
            operation=lambda: self._send(external_params),
        )
