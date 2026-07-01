from datetime import UTC, datetime

from app.modules.data_sources.freshness import (
    MarketDataFreshness,
    evaluate_market_data_freshness,
)


def freshness(
    *, event_time: datetime, received_at: datetime, now: datetime
) -> MarketDataFreshness:
    return evaluate_market_data_freshness(
        timeframe="1d",
        event_time=event_time,
        received_at=received_at,
        stale_after_hours=36,
        session_close_hour_utc=21,
        now=now,
    )


def test_yesterday_daily_bar_received_today_is_not_stale_before_close() -> None:
    result = freshness(
        event_time=datetime(2026, 6, 30, 0, 0, tzinfo=UTC),
        received_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        now=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
    )

    assert result.is_fetch_stale is False
    assert result.is_market_data_stale is False
    assert result.is_stale is False


def test_weekend_does_not_require_a_new_market_session() -> None:
    result = freshness(
        event_time=datetime(2026, 6, 26, 0, 0, tzinfo=UTC),
        received_at=datetime(2026, 6, 26, 22, 0, tzinfo=UTC),
        now=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )

    assert result.expected_session_date.isoformat() == "2026-06-26"
    assert result.is_market_data_stale is False


def test_monday_before_close_expects_friday_session() -> None:
    result = freshness(
        event_time=datetime(2026, 6, 26, 0, 0, tzinfo=UTC),
        received_at=datetime(2026, 6, 29, 14, 0, tzinfo=UTC),
        now=datetime(2026, 6, 29, 15, 0, tzinfo=UTC),
    )

    assert result.expected_session_date.isoformat() == "2026-06-26"
    assert result.is_market_data_stale is False
    assert result.is_fetch_stale is False


def test_after_close_missing_current_session_is_market_stale() -> None:
    result = freshness(
        event_time=datetime(2026, 6, 30, 0, 0, tzinfo=UTC),
        received_at=datetime(2026, 7, 1, 20, 0, tzinfo=UTC),
        now=datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
    )

    assert result.is_fetch_stale is False
    assert result.is_market_data_stale is True


def test_fetch_age_is_independent_from_market_session_date() -> None:
    result = freshness(
        event_time=datetime(2026, 6, 26, 0, 0, tzinfo=UTC),
        received_at=datetime(2026, 6, 24, 0, 0, tzinfo=UTC),
        now=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )

    assert result.is_fetch_stale is True
    assert result.is_market_data_stale is False
