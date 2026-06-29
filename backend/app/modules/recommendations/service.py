from decimal import Decimal
from typing import Literal


def composite_rating(scores: list[Decimal]) -> tuple[Literal["BUY", "HOLD", "SELL"], Decimal]:
    if not scores:
        raise ValueError("at least one score is required")
    score = (sum(scores) / len(scores)).quantize(Decimal("0.01"))
    if score >= Decimal("75"):
        return "BUY", score
    if score < Decimal("45"):
        return "SELL", score
    return "HOLD", score

