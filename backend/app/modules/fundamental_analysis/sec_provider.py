from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.core.time import utc_now
from app.modules.fundamental_analysis.contracts import (
    FundamentalDataProvider,
    ResolvedCompany,
    SecCompanyNotFoundError,
    SecInvalidResponseError,
    SecRateLimitError,
    SecTimeoutError,
    SecUnavailableError,
    TickerCacheStore,
    normalize_cik,
    normalize_symbol,
)
from app.modules.fundamental_analysis.sec_gateway import SecEdgarRequestGateway


class SecEdgarFundamentalDataProvider(FundamentalDataProvider):
    name = "sec_edgar"

    def __init__(
        self,
        gateway: SecEdgarRequestGateway,
        *,
        ticker_cache: TickerCacheStore | None = None,
        ticker_cache_ttl_hours: int = 168,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.gateway = gateway
        self.ticker_cache = ticker_cache
        self.ticker_cache_ttl_hours = ticker_cache_ttl_hours
        self.now = now
        self._resolved_companies: dict[str, ResolvedCompany] = {}

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        return normalize_symbol(symbol)

    @staticmethod
    def _parse_ticker_index(payload: dict[str, Any]) -> list[ResolvedCompany]:
        fields = payload.get("fields")
        rows = payload.get("data")
        if not isinstance(fields, list) or not isinstance(rows, list):
            raise SecInvalidResponseError("SEC ticker index fields are missing")
        positions = {str(field).lower(): index for index, field in enumerate(fields)}
        required = {"cik", "name", "ticker"}
        if not required.issubset(positions):
            raise SecInvalidResponseError("SEC ticker index columns are missing")

        companies: dict[str, ResolvedCompany] = {}
        for row in rows:
            if not isinstance(row, list):
                continue
            try:
                symbol = normalize_symbol(str(row[positions["ticker"]]))
                legal_name = str(row[positions["name"]]).strip()
                if not legal_name:
                    raise ValueError("missing legal name")
                exchange = (
                    str(row[positions["exchange"]]).strip()[:80]
                    if "exchange" in positions and row[positions["exchange"]]
                    else None
                )
                companies[symbol] = ResolvedCompany(
                    symbol=symbol,
                    cik=normalize_cik(row[positions["cik"]]),
                    legal_name=legal_name[:240],
                    exchange=exchange,
                )
            except (IndexError, TypeError, ValueError):
                continue
        if not companies:
            raise SecInvalidResponseError("SEC ticker index contains no valid companies")
        return list(companies.values())

    async def resolve_company(self, symbol: str) -> ResolvedCompany:
        normalized = self.normalize_symbol(symbol)
        cached = self._resolved_companies.get(normalized)
        if cached is not None:
            return cached
        persistent = None
        is_fresh = False
        if self.ticker_cache is not None:
            persistent, is_fresh = self.ticker_cache.get_cached_company(
                normalized,
                ttl_hours=self.ticker_cache_ttl_hours,
                now=self.now(),
            )
            if persistent is not None and is_fresh:
                self._resolved_companies[normalized] = persistent
                return persistent

        try:
            payload = await self.gateway.get_ticker_index()
        except (SecRateLimitError, SecTimeoutError, SecUnavailableError):
            if persistent is None:
                raise
            stale = persistent.model_copy(update={"warning": "sec_ticker_cache_stale"})
            self._resolved_companies[normalized] = stale
            return stale

        companies = self._parse_ticker_index(payload)
        if self.ticker_cache is not None:
            self.ticker_cache.store_cached_companies(companies, fetched_at=self.now())
        company = next((item for item in companies if item.symbol == normalized), None)
        if company is None:
            raise SecCompanyNotFoundError("Ticker is not present in the SEC index")
        self._resolved_companies[normalized] = company
        return company

    async def get_company_profile(self, symbol: str) -> dict[str, Any]:
        company = await self.resolve_company(symbol)
        return await self.get_submissions(company.cik)

    async def get_submissions(self, cik: str) -> dict[str, Any]:
        return await self.gateway.get_submissions(normalize_cik(cik))

    async def get_company_facts(self, cik: str) -> dict[str, Any]:
        return await self.gateway.get_company_facts(normalize_cik(cik))
