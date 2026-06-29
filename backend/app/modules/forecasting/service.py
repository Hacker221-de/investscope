from decimal import Decimal


def linear_projection(values: list[Decimal], periods: int) -> list[Decimal]:
    if periods < 0:
        raise ValueError("periods cannot be negative")
    if len(values) < 2:
        return values[-1:] * periods
    step = (values[-1] - values[0]) / Decimal(len(values) - 1)
    return [(values[-1] + step * index).quantize(Decimal("0.01")) for index in range(1, periods + 1)]

