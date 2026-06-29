from decimal import Decimal


def max_drawdown(equity_curve: list[Decimal]) -> Decimal:
    if not equity_curve:
        return Decimal("0.00")
    peak = equity_curve[0]
    worst = Decimal("0")
    for value in equity_curve:
        if value <= 0:
            raise ValueError("equity values must be positive")
        peak = max(peak, value)
        drawdown = (peak - value) / peak * Decimal("100")
        worst = max(worst, drawdown)
    return worst.quantize(Decimal("0.01"))


def position_weight(position_value: Decimal, portfolio_value: Decimal) -> Decimal:
    if portfolio_value <= 0:
        raise ValueError("portfolio_value must be positive")
    return (position_value / portfolio_value * Decimal("100")).quantize(Decimal("0.01"))

