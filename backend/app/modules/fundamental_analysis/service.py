from decimal import Decimal


def fundamental_score(
    return_on_equity: Decimal, debt_to_equity: Decimal, revenue_growth: Decimal
) -> Decimal:
    """Return a bounded 0-100 illustrative quality score."""
    raw = Decimal("50") + return_on_equity * Decimal("80") - debt_to_equity * Decimal("15")
    raw += revenue_growth * Decimal("60")
    return min(Decimal("100"), max(Decimal("0"), raw)).quantize(Decimal("0.01"))

