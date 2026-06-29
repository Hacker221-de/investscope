from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.time import ensure_utc
from app.modules.portfolio import DISCLAIMER, OwnedPosition, analyze_portfolio, calculate_market_value


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        ensure_utc(datetime(2026, 6, 29, 12, 0))


def test_aware_datetimes_are_normalized_to_utc() -> None:
    source = datetime(2026, 6, 29, 15, 0, tzinfo=timezone(timedelta(hours=3)))

    assert ensure_utc(source) == datetime(2026, 6, 29, 12, 0, tzinfo=UTC)


def test_money_calculation_keeps_decimal_precision() -> None:
    assert calculate_market_value(Decimal("3.25"), Decimal("19.99")) == Decimal("64.97")


def test_owned_position_analysis_uses_purchase_cost_and_fees() -> None:
    position = OwnedPosition(
        id=1,
        symbol="AAPL",
        quantity=Decimal("2"),
        average_purchase_price=Decimal("100"),
        purchase_date=datetime(2025, 1, 1, tzinfo=UTC).date(),
        currency="USD",
        fees=Decimal("5"),
        sector="Technology",
        geography="United States",
        current_price=Decimal("120"),
    )

    result = analyze_portfolio("Owned assets", "USD", [position], datetime.now(UTC))

    assert result["current_value"] == Decimal("240.00")
    assert result["invested_capital"] == Decimal("205.00")
    assert result["unrealized_pnl"] == Decimal("35.00")
    assert result["total_return_percent"] == Decimal("17.07")
    assert result["disclaimer"] == DISCLAIMER
