from datetime import date, timedelta
from decimal import Decimal
from math import sqrt
from typing import Literal, TypedDict

from app.modules.risk.service import max_drawdown


class BacktestCalculation(TypedDict):
    final_value: Decimal
    benchmark_final_value: Decimal
    total_return_percent: Decimal
    benchmark_return_percent: Decimal
    max_drawdown_percent: Decimal
    sharpe_ratio: Decimal
    signals: int
    correct_signals: int
    incorrect_signals: int
    strategy_curve: list[Decimal]
    benchmark_curve: list[Decimal]


def fixed_demo_series(start: date, end: date) -> tuple[list[date], list[Decimal]]:
    """Return a deterministic weekday series; it contains no external or future data."""
    if start >= end:
        raise ValueError("start date must be earlier than end date")

    anchor = date(2024, 1, 1)
    dates: list[date] = []
    prices: list[Decimal] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            index = (current - anchor).days
            cycle = index % 42
            triangle = cycle if cycle <= 21 else 42 - cycle
            secondary = (index * 7) % 19
            value = (
                Decimal("92")
                + Decimal(index) * Decimal("0.035")
                + (Decimal(triangle) - Decimal("10.5")) * Decimal("0.72")
                + (Decimal(secondary) - Decimal("9")) * Decimal("0.17")
            )
            dates.append(current)
            prices.append(max(value.quantize(Decimal("0.01")), Decimal("1.00")))
        current += timedelta(days=1)
    if len(prices) < 2:
        raise ValueError("selected period contains fewer than two demo observations")
    return dates, prices


def _sma(prices: list[Decimal], end_index: int, window: int) -> Decimal:
    values = prices[end_index - window + 1:end_index + 1]
    return sum(values, Decimal("0")) / Decimal(window)


def _sharpe_ratio(curve: list[Decimal]) -> Decimal:
    returns = [float(curve[index] / curve[index - 1] - Decimal("1")) for index in range(1, len(curve))]
    if not returns:
        return Decimal("0.00")
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    if variance == 0:
        return Decimal("0.00")
    return Decimal(str(mean / sqrt(variance) * sqrt(252))).quantize(Decimal("0.01"))


def sma_crossover_analysis(
    prices: list[Decimal],
    initial_capital: Decimal,
    short_window: int,
    long_window: int,
    method: Literal["moving", "hold"] = "moving",
) -> BacktestCalculation:
    """Evaluate analytical SMA signals on a fixed price series without creating orders."""
    if len(prices) < 2 or any(price <= 0 for price in prices):
        raise ValueError("at least two positive prices are required")
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    if short_window <= 0:
        raise ValueError("short_window must be positive")
    if long_window <= short_window:
        raise ValueError("long_window must be greater than short_window")
    if method == "moving" and len(prices) < long_window:
        raise ValueError("selected period is shorter than long_window")

    benchmark_curve = [
        (initial_capital * price / prices[0]).quantize(Decimal("0.01"))
        for price in prices
    ]
    signal_state: list[bool | None] = [None] * len(prices)
    if method == "moving":
        for index in range(long_window - 1, len(prices)):
            signal_state[index] = _sma(prices, index, short_window) > _sma(prices, index, long_window)

    strategy_curve = [initial_capital]
    for index in range(1, len(prices)):
        active = method == "hold" or signal_state[index - 1] is True
        next_value = strategy_curve[-1]
        if active:
            next_value *= prices[index] / prices[index - 1]
        strategy_curve.append(next_value.quantize(Decimal("0.01")))

    signal_indexes: list[int] = []
    if method == "moving":
        previous: bool | None = None
        for index, state in enumerate(signal_state):
            if state is None:
                continue
            if previous is not None and state != previous:
                signal_indexes.append(index)
            previous = state

    correct = 0
    for signal_position, index in enumerate(signal_indexes):
        comparison_index = signal_indexes[signal_position + 1] if signal_position + 1 < len(signal_indexes) else len(prices) - 1
        movement = prices[comparison_index] - prices[index]
        state = signal_state[index]
        if (state is True and movement > 0) or (state is False and movement < 0):
            correct += 1

    total_return = (strategy_curve[-1] / initial_capital - Decimal("1")) * Decimal("100")
    benchmark_return = (benchmark_curve[-1] / initial_capital - Decimal("1")) * Decimal("100")
    return {
        "final_value": strategy_curve[-1],
        "benchmark_final_value": benchmark_curve[-1],
        "total_return_percent": total_return.quantize(Decimal("0.01")),
        "benchmark_return_percent": benchmark_return.quantize(Decimal("0.01")),
        "max_drawdown_percent": max_drawdown(strategy_curve),
        "sharpe_ratio": _sharpe_ratio(strategy_curve),
        "signals": len(signal_indexes),
        "correct_signals": correct,
        "incorrect_signals": len(signal_indexes) - correct,
        "strategy_curve": strategy_curve,
        "benchmark_curve": benchmark_curve,
    }


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
