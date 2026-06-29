from decimal import Decimal

import pytest

from app.modules.backtesting import backtest_summary
from app.modules.recommendations import composite_rating
from app.modules.risk import max_drawdown
from app.modules.valuation import discounted_cash_flow


def test_discounted_cash_flow_uses_decimal_math() -> None:
    value = discounted_cash_flow(
        [Decimal("100.00"), Decimal("110.00")],
        Decimal("0.10"),
        terminal_value=Decimal("500.00"),
    )

    assert value == Decimal("595.04")


def test_composite_rating_boundaries() -> None:
    assert composite_rating([Decimal("80"), Decimal("70")]) == ("BUY", Decimal("75.00"))
    assert composite_rating([Decimal("44")]) == ("SELL", Decimal("44.00"))


def test_max_drawdown() -> None:
    result = max_drawdown([Decimal("100"), Decimal("120"), Decimal("90"), Decimal("110")])

    assert result == Decimal("25.00")


def test_backtest_rejects_invalid_prices() -> None:
    with pytest.raises(ValueError, match="positive prices"):
        backtest_summary([Decimal("100"), Decimal("0")], Decimal("10000"))

