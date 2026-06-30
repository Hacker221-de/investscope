from datetime import UTC, date, datetime
from decimal import Decimal

from app.modules.portfolio import OwnedPosition, analyze_portfolio


def test_portfolio_excludes_unvalued_position_from_return() -> None:
    valued = OwnedPosition(
        id=1, symbol="AAPL", quantity=Decimal("2"),
        average_purchase_price=Decimal("100"), purchase_date=date(2025, 1, 1),
        currency="USD", fees=None, sector="Technology", geography="US",
        current_price=Decimal("120"), price_source="alpha_vantage",
        price_updated_at=datetime(2026, 6, 30, tzinfo=UTC), price_is_stale=False,
    )
    unvalued = OwnedPosition(
        id=2, symbol="MISSING", quantity=Decimal("10"),
        average_purchase_price=Decimal("50"), purchase_date=date(2025, 1, 1),
        currency="USD", fees=None, sector="Other", geography="US",
        current_price=None,
    )

    result = analyze_portfolio(
        "Owned assets", "USD", [valued, unvalued], datetime(2026, 6, 30, tzinfo=UTC),
    )

    assert result["current_value"] == Decimal("240.00")
    assert result["invested_capital"] == Decimal("200.00")
    assert result["recorded_invested_capital"] == Decimal("700.00")
    assert result["unrealized_pnl"] == Decimal("40.00")
    assert result["total_return_percent"] == Decimal("20.00")
    assert result["unvalued_positions_count"] == 1
    assert result["positions"][1]["current_value"] is None
