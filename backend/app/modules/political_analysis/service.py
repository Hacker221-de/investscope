from decimal import Decimal


def political_risk_score(event_weights: list[Decimal]) -> Decimal:
    if not event_weights:
        return Decimal("0.00")
    average = sum(event_weights) / len(event_weights)
    return min(Decimal("100"), max(Decimal("0"), average)).quantize(Decimal("0.01"))

