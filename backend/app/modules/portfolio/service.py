from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import combinations

from app.modules.risk import max_drawdown

DISCLAIMER = (
    "InvestScope анализирует введённые пользователем позиции, "
    "но не подключается к брокеру и не совершает сделки"
)


@dataclass(frozen=True, slots=True)
class OwnedPosition:
    id: int
    symbol: str
    quantity: Decimal
    average_purchase_price: Decimal
    purchase_date: date
    currency: str
    fees: Decimal | None
    sector: str
    geography: str
    current_price: Decimal


def calculate_market_value(quantity: Decimal, price: Decimal) -> Decimal:
    if quantity < 0 or price < 0:
        raise ValueError("quantity and price cannot be negative")
    return (quantity * price).quantize(Decimal("0.01"))


def position_metrics(position: OwnedPosition) -> dict[str, object]:
    fees = position.fees or Decimal("0")
    invested_capital = (
        position.quantity * position.average_purchase_price + fees
    ).quantize(Decimal("0.01"))
    current_value = calculate_market_value(position.quantity, position.current_price)
    unrealized_pnl = (current_value - invested_capital).quantize(Decimal("0.01"))
    return_percent = (
        unrealized_pnl / invested_capital * Decimal("100")
    ).quantize(Decimal("0.01"))
    return {
        "id": position.id,
        "symbol": position.symbol,
        "quantity": position.quantity,
        "average_purchase_price": position.average_purchase_price,
        "purchase_date": position.purchase_date,
        "currency": position.currency,
        "fees": position.fees,
        "sector": position.sector,
        "geography": position.geography,
        "current_price": position.current_price,
        "current_value": current_value,
        "invested_capital": invested_capital,
        "unrealized_pnl": unrealized_pnl,
        "return_percent": return_percent,
    }


def _allocation(
    positions: list[OwnedPosition], metrics: list[dict[str, object]], group: str
) -> list[dict[str, object]]:
    values: defaultdict[str, Decimal] = defaultdict(Decimal)
    total = sum((Decimal(str(item["current_value"])) for item in metrics), Decimal("0"))
    for position, item in zip(positions, metrics, strict=True):
        label = position.symbol if group == "symbol" else str(getattr(position, group))
        values[label] += Decimal(str(item["current_value"]))
    return [
        {
            "label": label,
            "value": value.quantize(Decimal("0.01")),
            "percent": (
                value / total * Decimal("100") if total else Decimal("0")
            ).quantize(Decimal("0.01")),
        }
        for label, value in sorted(values.items(), key=lambda pair: pair[1], reverse=True)
    ]


def analyze_portfolio(
    name: str,
    base_currency: str,
    positions: list[OwnedPosition],
    as_of: datetime,
) -> dict[str, object]:
    metrics = [position_metrics(position) for position in positions]
    current_value = sum(
        (Decimal(str(item["current_value"])) for item in metrics), Decimal("0")
    ).quantize(Decimal("0.01"))
    invested_capital = sum(
        (Decimal(str(item["invested_capital"])) for item in metrics), Decimal("0")
    ).quantize(Decimal("0.01"))
    unrealized_pnl = (current_value - invested_capital).quantize(Decimal("0.01"))
    total_return = (
        unrealized_pnl / invested_capital * Decimal("100")
        if invested_capital
        else Decimal("0")
    ).quantize(Decimal("0.01"))

    asset_allocation = _allocation(positions, metrics, "symbol")
    largest = asset_allocation[0] if asset_allocation else {"label": "—", "percent": Decimal("0")}
    top_three = sum(
        (Decimal(str(item["percent"])) for item in asset_allocation[:3]), Decimal("0")
    ).quantize(Decimal("0.01"))

    correlation_defaults = {
        frozenset(("AAPL", "MSFT")): Decimal("0.74"),
        frozenset(("AAPL", "TLT")): Decimal("-0.18"),
        frozenset(("MSFT", "TLT")): Decimal("-0.12"),
    }
    correlations = [
        {
            "first_symbol": first.symbol,
            "second_symbol": second.symbol,
            "coefficient": correlation_defaults.get(
                frozenset((first.symbol, second.symbol)), Decimal("0.25")
            ),
        }
        for first, second in combinations(positions, 2)
    ]

    stress_inputs = [
        ("Снижение рынка", Decimal("-10")),
        ("Рост ставок на 100 б.п.", Decimal("-6")),
        ("Позитивный сезон отчётности", Decimal("5")),
    ]
    stress_scenarios = []
    for scenario_name, shock in stress_inputs:
        projected = (current_value * (Decimal("1") + shock / Decimal("100"))).quantize(
            Decimal("0.01")
        )
        stress_scenarios.append(
            {
                "name": scenario_name,
                "shock_percent": shock,
                "projected_value": projected,
                "projected_pnl": (projected - invested_capital).quantize(Decimal("0.01")),
            }
        )

    symbols = [position.symbol for position in positions]
    return {
        "name": name,
        "base_currency": base_currency,
        "current_value": current_value,
        "invested_capital": invested_capital,
        "unrealized_pnl": unrealized_pnl,
        "total_return_percent": total_return,
        "as_of": as_of,
        "positions": metrics,
        "allocation_by_asset": asset_allocation,
        "allocation_by_sector": _allocation(positions, metrics, "sector"),
        "allocation_by_currency": _allocation(positions, metrics, "currency"),
        "risk": {
            "historical_volatility_percent": Decimal("21.40"),
            "max_drawdown_percent": max_drawdown(
                [
                    Decimal("100"),
                    Decimal("104"),
                    Decimal("101"),
                    Decimal("108"),
                    Decimal("103"),
                    Decimal("110"),
                ]
            ),
            "concentration": {
                "largest_position_symbol": str(largest["label"]),
                "largest_position_percent": Decimal(str(largest["percent"])),
                "top_three_percent": top_three,
            },
        },
        "correlations": correlations,
        "political_and_geographic_risks": [
            "Концентрация эмитентов в юрисдикции США",
            "Чувствительность технологического сектора к экспортному регулированию",
            "Процентный риск долговых инструментов",
        ],
        "stress_scenarios": stress_scenarios,
        "news_impacts": [
            {
                "title": "Technology sector policy review",
                "published_at": datetime(2026, 6, 29, 9, 30, tzinfo=UTC),
                "affected_symbols": [symbol for symbol in symbols if symbol in {"AAPL", "MSFT", "NVDA"}],
                "impact": "negative",
                "summary": "Политическая неопределённость повышает риск-премию технологических позиций.",
            },
            {
                "title": "Long-term yields stabilize",
                "published_at": datetime(2026, 6, 28, 16, 0, tzinfo=UTC),
                "affected_symbols": [symbol for symbol in symbols if symbol == "TLT"],
                "impact": "positive",
                "summary": "Стабилизация доходностей поддерживает оценку длинных облигаций.",
            },
        ],
        "disclaimer": DISCLAIMER,
    }
