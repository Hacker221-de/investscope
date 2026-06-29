from decimal import Decimal
from typing import Literal


def moving_average_signal(
    prices: list[Decimal], short_window: int = 5, long_window: int = 20
) -> Literal["bullish", "neutral", "bearish"]:
    if short_window <= 0 or long_window <= short_window:
        raise ValueError("windows must be positive and long_window must exceed short_window")
    if len(prices) < long_window:
        return "neutral"
    short_average = sum(prices[-short_window:]) / short_window
    long_average = sum(prices[-long_window:]) / long_window
    if short_average > long_average:
        return "bullish"
    if short_average < long_average:
        return "bearish"
    return "neutral"

