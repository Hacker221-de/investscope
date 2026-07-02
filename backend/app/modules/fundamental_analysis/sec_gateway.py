import asyncio
import logging
import time
import weakref
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.fundamental_analysis.contracts import (
    SecAccessDeniedError,
    SecCompanyNotFoundError,
    SecInvalidResponseError,
    SecRateLimitError,
    SecTimeoutError,
    SecUnavailableError,
    normalize_cik,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _CacheEntry:
    expires_at: float
    value: Any


class SecResponseCache:
    def __init__(self) -> None:
        self._entries: dict[str, _CacheEntry] = {}

    def get(self, key: str, now: float) -> Any | None:
        entry = self._entries.get(key)
        if entry is None or entry.expires_at <= now:
            self._entries.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: Any, expires_at: float) -> None:
        self._entries[key] = _CacheEntry(expires_at=expires_at, value=value)

    def clear(self) -> None:
        self._entries.clear()


_SHARED_CACHE = SecResponseCache()


@dataclass(slots=True)
class _ThrottleState:
    lock: asyncio.Lock
    last_started: float | None = None


_THROTTLE_STATES: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, _ThrottleState
] = weakref.WeakKeyDictionary()
_CLIENTS: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, dict[tuple[str, float], httpx.AsyncClient]
] = weakref.WeakKeyDictionary()


class SecEdgarRequestGateway:
    ticker_url = "https://www.sec.gov/files/company_tickers_exchange.json"
    submissions_base_url = "https://data.sec.gov/submissions"
    companyfacts_base_url = "https://data.sec.gov/api/xbrl/companyfacts"
    advisory_lock_key = 7_315_352_459_946_821_457

    def __init__(
        self,
        *,
        user_agent: str,
        max_requests_per_second: float,
        cache_ttl_hours: int,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
        cache: SecResponseCache | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        session: Session | None = None,
    ) -> None:
        if not user_agent.strip() or user_agent.lower().startswith("python-httpx"):
            raise ValueError("SEC User-Agent must identify the application and contact")
        if max_requests_per_second <= 0 or max_requests_per_second > 10:
            raise ValueError("SEC request rate must be between 0 and 10 requests per second")
        self.user_agent = user_agent.strip()
        self.minimum_interval = 1 / max_requests_per_second
        self.cache_ttl_seconds = cache_ttl_hours * 3600
        self.timeout_seconds = timeout_seconds
        self.client = client
        self.cache = cache or _SHARED_CACHE
        self.monotonic = monotonic
        self.sleep = sleep
        self.session = session

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json",
        }

    def _shared_client(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        clients = _CLIENTS.setdefault(loop, {})
        key = (self.user_agent, self.timeout_seconds)
        client = clients.get(key)
        if client is None:
            client = httpx.AsyncClient(
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            clients[key] = client
        return client

    async def _acquire_throttle(self) -> _ThrottleState:
        loop = asyncio.get_running_loop()
        state = _THROTTLE_STATES.get(loop)
        if state is None:
            state = _ThrottleState(lock=asyncio.Lock())
            _THROTTLE_STATES[loop] = state
        await state.lock.acquire()
        return state

    async def _wait_for_interval(self, state: _ThrottleState) -> None:
        if state.last_started is not None:
            wait = self.minimum_interval - (self.monotonic() - state.last_started)
            if wait > 0:
                await self.sleep(wait)
        state.last_started = self.monotonic()

    def _acquire_postgresql_lock(self) -> None:
        if self.session is None:
            return
        bind = self.session.get_bind()
        if bind.dialect.name == "postgresql":
            self.session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": self.advisory_lock_key},
            )

    @staticmethod
    def _is_rate_threshold_response(response: httpx.Response) -> bool:
        body = response.text[:4096].casefold()
        if "undeclared automated tool" in body:
            return False
        return any(
            marker in body
            for marker in (
                "request rate threshold exceeded",
                "rate threshold",
                "excessive requests",
            )
        )

    async def _request_json(self, *, endpoint: str, url: str) -> Any:
        throttle = await self._acquire_throttle()
        try:
            self._acquire_postgresql_lock()
            await self._wait_for_interval(throttle)
            logger.info("SEC EDGAR request endpoint=%s", endpoint)
            client = self.client or self._shared_client()
            response = await client.get(url, headers=self._headers())
        except httpx.TimeoutException:
            raise SecTimeoutError("SEC request timed out") from None
        except httpx.HTTPError:
            raise SecUnavailableError("SEC is unavailable") from None
        finally:
            throttle.lock.release()

        if response.status_code == 403 and self._is_rate_threshold_response(response):
            raise SecRateLimitError("SEC rate threshold reached")
        if response.status_code == 403:
            raise SecAccessDeniedError("SEC access denied")
        if response.status_code == 404:
            raise SecCompanyNotFoundError("SEC company was not found")
        if response.status_code == 429:
            raise SecRateLimitError("SEC rate limit reached")
        if response.status_code >= 400:
            raise SecUnavailableError("SEC is unavailable")
        try:
            payload = response.json()
        except ValueError:
            raise SecInvalidResponseError("SEC returned malformed JSON") from None
        if not isinstance(payload, (dict, list)):
            raise SecInvalidResponseError("SEC returned an unexpected JSON shape")
        return payload

    async def get_json(self, *, cache_key: str, endpoint: str, url: str) -> Any:
        now = self.monotonic()
        cached = self.cache.get(cache_key, now)
        if cached is not None:
            return cached
        payload = await self._request_json(endpoint=endpoint, url=url)
        self.cache.set(cache_key, payload, self.monotonic() + self.cache_ttl_seconds)
        return payload

    async def get_ticker_index(self) -> dict[str, Any]:
        payload = await self.get_json(
            cache_key="sec:ticker-index",
            endpoint="company_tickers_exchange",
            url=self.ticker_url,
        )
        if not isinstance(payload, dict):
            raise SecInvalidResponseError("SEC ticker index has an invalid shape")
        return payload

    async def get_submissions(self, cik: str) -> dict[str, Any]:
        cik = normalize_cik(cik)
        payload = await self.get_json(
            cache_key=f"sec:submissions:{cik}",
            endpoint="submissions",
            url=f"{self.submissions_base_url}/CIK{cik}.json",
        )
        if not isinstance(payload, dict):
            raise SecInvalidResponseError("SEC submissions response has an invalid shape")
        return payload

    async def get_company_facts(self, cik: str) -> dict[str, Any]:
        cik = normalize_cik(cik)
        payload = await self.get_json(
            cache_key=f"sec:companyfacts:{cik}",
            endpoint="companyfacts",
            url=f"{self.companyfacts_base_url}/CIK{cik}.json",
        )
        if not isinstance(payload, dict):
            raise SecInvalidResponseError("SEC company facts response has an invalid shape")
        return payload
