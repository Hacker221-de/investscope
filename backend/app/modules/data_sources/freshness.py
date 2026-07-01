from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.core.time import ensure_utc, utc_now


@dataclass(frozen=True, slots=True)
class MarketDataFreshness:
    is_fetch_stale: bool
    is_market_data_stale: bool
    expected_session_date: date | None

    @property
    def is_stale(self) -> bool:
        return self.is_fetch_stale or self.is_market_data_stale


def _previous_weekday(day: date) -> date:
    candidate = day - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def latest_expected_completed_session(
    now: datetime,
    *,
    session_close_hour_utc: int,
) -> date:
    current = ensure_utc(now)
    day = current.date()
    if day.weekday() >= 5:
        while day.weekday() >= 5:
            day -= timedelta(days=1)
        return day
    session_close = time(hour=session_close_hour_utc)
    if current.time().replace(tzinfo=None) < session_close:
        return _previous_weekday(day)
    return day


def evaluate_market_data_freshness(
    *,
    timeframe: str,
    event_time: datetime,
    received_at: datetime,
    stale_after_hours: int,
    session_close_hour_utc: int,
    now: datetime | None = None,
) -> MarketDataFreshness:
    current = ensure_utc(now) if now is not None else utc_now()
    normalized_event = ensure_utc(event_time)
    normalized_received = ensure_utc(received_at)
    is_fetch_stale = current - normalized_received > timedelta(hours=stale_after_hours)

    if timeframe == "1d":
        expected_session = latest_expected_completed_session(
            current,
            session_close_hour_utc=session_close_hour_utc,
        )
        is_market_data_stale = normalized_event.date() < expected_session
    else:
        expected_session = None
        is_market_data_stale = (
            current - normalized_event > timedelta(hours=stale_after_hours)
        )
    return MarketDataFreshness(
        is_fetch_stale=is_fetch_stale,
        is_market_data_stale=is_market_data_stale,
        expected_session_date=expected_session,
    )
