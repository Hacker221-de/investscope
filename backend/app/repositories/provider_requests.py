from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ProviderRequestLog


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    requests_used_today: int
    last_request_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    last_error_at: datetime | None


class ProviderRequestRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _day_bounds(now: datetime) -> tuple[datetime, datetime]:
        start = datetime(now.year, now.month, now.day, tzinfo=UTC)
        return start, start + timedelta(days=1)

    def requests_used_today(self, provider: str, now: datetime) -> int:
        start, end = self._day_bounds(now)
        return int(self.session.scalar(
            select(func.count()).select_from(ProviderRequestLog).where(
                ProviderRequestLog.provider == provider,
                ProviderRequestLog.requested_at >= start,
                ProviderRequestLog.requested_at < end,
            )
        ) or 0)

    def last_request_at(self, provider: str) -> datetime | None:
        return self.session.scalar(
            select(ProviderRequestLog.started_at)
            .where(ProviderRequestLog.provider == provider)
            .order_by(ProviderRequestLog.requested_at.desc())
            .limit(1)
        )

    def last_success_at(self, provider: str) -> datetime | None:
        return self.session.scalar(
            select(ProviderRequestLog.completed_at)
            .where(
                ProviderRequestLog.provider == provider,
                ProviderRequestLog.successful.is_(True),
            )
            .order_by(ProviderRequestLog.completed_at.desc())
            .limit(1)
        )

    def last_error(self, provider: str) -> str | None:
        return self.session.scalar(
            select(ProviderRequestLog.error_type)
            .where(
                ProviderRequestLog.provider == provider,
                ProviderRequestLog.successful.is_(False),
            )
            .order_by(ProviderRequestLog.completed_at.desc())
            .limit(1)
        )

    def last_error_at(self, provider: str) -> datetime | None:
        return self.session.scalar(
            select(ProviderRequestLog.completed_at)
            .where(
                ProviderRequestLog.provider == provider,
                ProviderRequestLog.successful.is_(False),
            )
            .order_by(ProviderRequestLog.completed_at.desc())
            .limit(1)
        )

    def usage(self, provider: str, now: datetime) -> ProviderUsage:
        return ProviderUsage(
            requests_used_today=self.requests_used_today(provider, now),
            last_request_at=self.last_request_at(provider),
            last_success_at=self.last_success_at(provider),
            last_error=self.last_error(provider),
            last_error_at=self.last_error_at(provider),
        )

    def add(
        self,
        *,
        provider: str,
        endpoint: str,
        symbol: str,
        requested_at: datetime,
        started_at: datetime,
        completed_at: datetime,
        status_code: int | None,
        retry_after_seconds: int | None,
        successful: bool,
        error_type: str | None,
        request_group_id: str,
    ) -> ProviderRequestLog:
        entry = ProviderRequestLog(
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
        self.session.add(entry)
        self.session.flush()
        return entry
