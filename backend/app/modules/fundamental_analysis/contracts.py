import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


def normalize_cik(value: str | int) -> str:
    text = str(value).strip()
    if not text.isdigit() or len(text) > 10:
        raise ValueError("CIK must contain at most 10 digits")
    return text.zfill(10)


SYMBOL_PATTERN = re.compile(r"^[A-Z0-9.\-]{1,16}$")


def normalize_symbol(value: str) -> str:
    normalized = value.strip().upper()
    if not SYMBOL_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid ticker symbol")
    return normalized


class ResolvedCompany(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str = Field(pattern=r"^[A-Z0-9.\-]{1,16}$")
    cik: str = Field(pattern=r"^[0-9]{10}$")
    legal_name: str
    exchange: str | None = None
    warning: str | None = None


class TickerCacheStore(Protocol):
    def get_cached_company(
        self, symbol: str, *, ttl_hours: int, now: datetime
    ) -> tuple[ResolvedCompany | None, bool]:
        ...

    def store_cached_companies(
        self, companies: list[ResolvedCompany], *, fetched_at: datetime
    ) -> None:
        ...


class FundamentalDataProvider(ABC):
    name: str

    @abstractmethod
    async def resolve_company(self, symbol: str) -> ResolvedCompany:
        raise NotImplementedError

    @abstractmethod
    async def get_company_profile(self, symbol: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def get_submissions(self, cik: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def get_company_facts(self, cik: str) -> dict[str, Any]:
        raise NotImplementedError


class SecProviderError(RuntimeError):
    code = "sec_unavailable"
    http_status = 502


class SecCompanyNotFoundError(SecProviderError):
    code = "sec_company_not_found"
    http_status = 404


class SecRateLimitError(SecProviderError):
    code = "sec_rate_limit"
    http_status = 429


class SecAccessDeniedError(SecProviderError):
    code = "sec_access_denied"
    http_status = 403


class SecTimeoutError(SecProviderError):
    code = "sec_timeout"
    http_status = 504


class SecInvalidResponseError(SecProviderError):
    code = "sec_invalid_response"
    http_status = 502


class SecUnavailableError(SecProviderError):
    code = "sec_unavailable"
    http_status = 503
