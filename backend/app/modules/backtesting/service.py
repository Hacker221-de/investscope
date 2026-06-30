from decimal import Decimal

from app.modules.risk.service import max_drawdown


def backtest_summary(prices: list[Decimal], initial_capital: Decimal) -> dict[str, Decimal | int]:
    """Passive analytical benchmark for deterministic unit tests and demo responses."""
    if len(prices) < 2 or any(price <= 0 for price in prices):
        raise ValueError("at least two positive prices are required")
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    units = initial_capital / prices[0]
    equity_curve = [(units * price).quantize(Decimal("0.01")) for price in prices]
    total_return = ((equity_curve[-1] / initial_capital) - Decimal("1")) * Decimal("100")
    return {
        "final_value": equity_curve[-1],
        "total_return_percent": total_return.quantize(Decimal("0.01")),
        "max_drawdown_percent": max_drawdown(equity_curve),
        "signals": 1,
    }
