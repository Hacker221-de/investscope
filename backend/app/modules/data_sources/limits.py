import asyncio
import hashlib
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TypeVar

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.time import utc_now
from app.modules.data_sources.contracts import (
    MarketDataProviderError,
    ProviderBurstLimitError,
    ProviderConfigurationError,
    ProviderDailyLimitError,
    ProviderInvalidRequestError,
    ProviderRateLimitError,
    ProviderSymbolNotFoundError,
    ProviderTimeoutError,
)
from app.repositories import ProviderRequestRepository, ProviderUsage

T = TypeVar("T")
_REQUEST_LOCKS: dict[tuple[int, object, str], asyncio.Lock] = {}
_LAST_STARTED_MONOTONIC: dict[tuple[object, str], float] = {}
_RATE_LIMITED_UNTIL: dict[tuple[str, object], datetime] = {}


@dataclass(frozen=True, slots=True)
class ProviderBudget:
    requests_used_today: int
    daily_limit: int | None
    remaining_requests: int | None
    last_request_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    retry_after_seconds: int | None


class ProviderRequestCoordinator:
    """Serialize, throttle and account for each individual external request."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        now: Callable[[], datetime] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.session = session
        self.settings = settings
        self.repository = ProviderRequestRepository(session)
        self.now = now
        self.monotonic = monotonic
        self.sleep = sleep

    @property
    def _bind_key(self) -> object:
        return self.session.get_bind()

    @property
    def _is_postgresql(self) -> bool:
        return self.session.get_bind().dialect.name == "postgresql"

    @staticmethod
    def _advisory_key(provider: str) -> int:
        return int.from_bytes(
            hashlib.blake2b(provider.encode("utf-8"), digest_size=8).digest(),
            byteorder="big",
            signed=True,
        )

    async def _acquire_interprocess_lock(self, provider: str) -> bool:
        if not self._is_postgresql:
            return False
        key = self._advisory_key(provider)
        poll_interval = min(
            max(self.settings.alpha_vantage_min_interval_seconds / 10, 0.05),
            0.25,
        )
        while not bool(self.session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)").bindparams(key=key)
        )):
            await self.sleep(poll_interval)
        return True

    def _release_interprocess_lock(self, provider: str, acquired: bool) -> None:
        # Transaction-scoped advisory locks are released atomically by commit.
        _ = provider, acquired

    def _daily_limit(self, provider: str) -> int | None:
        return self.settings.alpha_vantage_daily_limit if provider == "alpha_vantage" else None

    def _retry_after(self, provider: str, now: datetime, usage: ProviderUsage) -> int | None:
        blocked_until = _RATE_LIMITED_UNTIL.get((provider, self._bind_key))
        if blocked_until is None and usage.last_error in {
            "provider_burst_limit", "provider_rate_limit"
        }:
            if usage.last_error_at is not None and (
                usage.last_success_at is None or usage.last_success_at < usage.last_error_at
            ):
                blocked_until = usage.last_error_at + timedelta(
                    seconds=self.settings.alpha_vantage_rate_limit_cooldown_seconds
                )
        if blocked_until is None or blocked_until <= now:
            return None
        return max(1, math.ceil((blocked_until - now).total_seconds()))

    def budget(self, provider: str) -> ProviderBudget:
        now = self.now()
        usage = self.repository.usage(provider, now)
        daily_limit = self._daily_limit(provider)
        remaining = (
            max(daily_limit - usage.requests_used_today, 0)
            if daily_limit is not None else None
        )
        return ProviderBudget(
            requests_used_today=usage.requests_used_today,
            daily_limit=daily_limit,
            remaining_requests=remaining,
            last_request_at=usage.last_request_at,
            last_success_at=usage.last_success_at,
            last_error=usage.last_error,
            retry_after_seconds=self._retry_after(provider, now, usage),
        )

    def ensure_capacity(self, provider: str, required_requests: int = 1) -> None:
        if provider != "alpha_vantage":
            return
        budget = self.budget(provider)
        if budget.retry_after_seconds is not None:
            error_class = (
                ProviderBurstLimitError
                if budget.last_error == "provider_burst_limit"
                else ProviderRateLimitError
            )
            raise error_class(
                "Provider retry cooldown is active",
                retry_after_seconds=budget.retry_after_seconds,
                requests_used_today=budget.requests_used_today,
                daily_limit=budget.daily_limit,
            )
        daily_limit = budget.daily_limit or 0
        usable_limit = max(daily_limit - self.settings.alpha_vantage_daily_reserve, 0)
        if budget.requests_used_today + required_requests > usable_limit:
            raise ProviderDailyLimitError(
                "Provider daily request budget is exhausted",
                requests_used_today=budget.requests_used_today,
                daily_limit=daily_limit,
            )

    @staticmethod
    def _error_details(error: Exception) -> tuple[int | None, str]:
        if isinstance(error, ProviderBurstLimitError):
            return 429, "provider_burst_limit"
        if isinstance(error, ProviderDailyLimitError):
            return 429, "provider_daily_limit"
        if isinstance(error, ProviderRateLimitError):
            return 429, "provider_rate_limit"
        if isinstance(error, ProviderInvalidRequestError):
            return 502, "provider_invalid_request"
        if isinstance(error, ProviderSymbolNotFoundError):
            return 404, "provider_symbol_not_found"
        if isinstance(error, ProviderTimeoutError):
            return None, "provider_timeout"
        if isinstance(error, ProviderConfigurationError):
            return None, "provider_configuration"
        if isinstance(error, MarketDataProviderError):
            return 502, "provider_error"
        return None, "unexpected_error"

    def _record(
        self,
        *,
        provider: str,
        endpoint: str,
        symbol: str,
        requested_at: datetime,
        started_at: datetime,
        completed_at: datetime,
        request_group_id: str,
        status_code: int | None,
        retry_after_seconds: int | None,
        successful: bool,
        error_type: str | None,
    ) -> None:
        self.repository.add(
            provider=provider,
            endpoint=endpoint,
            symbol=symbol,
            requested_at=requested_at,
            started_at=started_at,
            completed_at=completed_at,
            status_code=status_code,
            retry_after_seconds=retry_after_seconds,
            successful=successful,
            error_type=error_type,
            request_group_id=request_group_id,
        )

    async def _wait_for_slot(self, provider: str, had_previous_request: bool) -> None:
        interval = self.settings.alpha_vantage_min_interval_seconds
        if interval <= 0:
            return
        key = (self._bind_key, provider)
        last_started = _LAST_STARTED_MONOTONIC.get(key)
        if self._is_postgresql and had_previous_request:
            wait = interval
        elif last_started is None:
            wait = 0.0
        else:
            wait = interval - (self.monotonic() - last_started)
        if wait > 0:
            await self.sleep(wait)

    async def request(
        self,
        *,
        provider: str,
        endpoint: str,
        symbol: str,
        request_group_id: str,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        if provider != "alpha_vantage":
            return await operation()

        requested_at = self.now()
        loop_id = id(asyncio.get_running_loop())
        lock = _REQUEST_LOCKS.setdefault(
            (loop_id, self._bind_key, provider), asyncio.Lock()
        )
        async with lock:
            advisory_acquired = await self._acquire_interprocess_lock(provider)
            try:
                self.ensure_capacity(provider)
                had_previous_request = self.repository.last_request_at(provider) is not None
                await self._wait_for_slot(provider, had_previous_request)
                started_at = self.now()
                _LAST_STARTED_MONOTONIC[(self._bind_key, provider)] = self.monotonic()
                try:
                    result = await operation()
                except Exception as error:
                    completed_at = self.now()
                    status_code, error_type = self._error_details(error)
                    retry_after = (
                        error.retry_after_seconds
                        if isinstance(error, ProviderRateLimitError) else None
                    )
                    self._record(
                        provider=provider,
                        endpoint=endpoint,
                        symbol=symbol,
                        requested_at=requested_at,
                        started_at=started_at,
                        completed_at=completed_at,
                        request_group_id=request_group_id,
                        status_code=status_code,
                        retry_after_seconds=retry_after,
                        successful=False,
                        error_type=error_type,
                    )
                    if isinstance(error, ProviderRateLimitError):
                        cooldown = retry_after
                        if cooldown is None:
                            cooldown = self.settings.alpha_vantage_rate_limit_cooldown_seconds
                        _RATE_LIMITED_UNTIL[(provider, self._bind_key)] = (
                            self.now() + timedelta(seconds=cooldown)
                        )
                        budget = self.budget(provider)
                        error.requests_used_today = budget.requests_used_today
                        error.daily_limit = budget.daily_limit
                        error.retry_after_seconds = cooldown
                    raise
                completed_at = self.now()
                self._record(
                    provider=provider,
                    endpoint=endpoint,
                    symbol=symbol,
                    requested_at=requested_at,
                    started_at=started_at,
                    completed_at=completed_at,
                    request_group_id=request_group_id,
                    status_code=200,
                    retry_after_seconds=None,
                    successful=True,
                    error_type=None,
                )
                return result
            finally:
                self._release_interprocess_lock(provider, advisory_acquired)
                self.session.commit()
