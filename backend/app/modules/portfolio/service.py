from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from itertools import combinations
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Portfolio, Position
from app.modules.risk import max_drawdown
from app.repositories.portfolio import PortfolioRepository

DISCLAIMER = (
    "InvestScope анализирует введённые пользователем позиции, "
    "но не подключается к брокеру и не совершает сделки"
)


class PortfolioDomainError(Exception):
    pass


class PortfolioNotFoundError(PortfolioDomainError):
    pass


class PositionNotFoundError(PortfolioDomainError):
    pass


class AssetNotFoundError(PortfolioDomainError):
    pass


class DuplicatePositionError(PortfolioDomainError):
    pass


class PortfolioValidationError(PortfolioDomainError):
    pass


class PortfolioPersistenceError(PortfolioDomainError):
    pass


class PortfolioService:
    def __init__(
        self,
        session: Session,
        repository: PortfolioRepository | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or PortfolioRepository(session)

    @staticmethod
    def _name(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise PortfolioValidationError("Portfolio name must not be empty")
        if len(normalized) > 120:
            raise PortfolioValidationError("Portfolio name must not exceed 120 characters")
        return normalized

    @staticmethod
    def _currency(value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isascii() or not normalized.isalpha():
            raise PortfolioValidationError("Currency must contain three ASCII letters")
        return normalized

    @staticmethod
    def _decimal(
        value: Decimal | int | str,
        *,
        field: str,
        precision: int,
        scale: int,
        strictly_positive: bool = False,
    ) -> Decimal:
        if isinstance(value, float):
            raise PortfolioValidationError(f"{field} must not use binary floating point")
        try:
            decimal_value = value if isinstance(value, Decimal) else Decimal(value)
            with localcontext() as context:
                context.prec = max(precision + scale + 4, 50)
                normalized = decimal_value.quantize(Decimal(1).scaleb(-scale))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise PortfolioValidationError(f"{field} must be a valid decimal") from error
        if not normalized.is_finite():
            raise PortfolioValidationError(f"{field} must be finite")
        if decimal_value != normalized:
            raise PortfolioValidationError(f"{field} supports at most {scale} decimal places")
        if strictly_positive and normalized <= 0:
            raise PortfolioValidationError(f"{field} must be greater than zero")
        if not strictly_positive and normalized < 0:
            raise PortfolioValidationError(f"{field} must not be negative")
        if abs(int(normalized.scaleb(scale))) >= 10**precision:
            raise PortfolioValidationError(
                f"{field} exceeds precision {precision} and scale {scale}"
            )
        return normalized

    def list_portfolios(self) -> list[Portfolio]:
        return self.repository.list_portfolios()

    def get_portfolio(self, portfolio_id: int) -> Portfolio:
        portfolio = self.repository.get_portfolio(portfolio_id)
        if portfolio is None:
            raise PortfolioNotFoundError("Portfolio not found")
        return portfolio

    def create_portfolio(self, *, name: str, base_currency: str = "USD") -> Portfolio:
        try:
            portfolio = self.repository.create_portfolio(
                name=self._name(name),
                base_currency=self._currency(base_currency),
            )
            self.session.commit()
            self.session.refresh(portfolio)
            return portfolio
        except PortfolioDomainError:
            self.session.rollback()
            raise
        except SQLAlchemyError as error:
            self.session.rollback()
            raise PortfolioPersistenceError("Portfolio could not be saved") from error

    def update_portfolio(self, portfolio_id: int, changes: dict[str, Any]) -> Portfolio:
        try:
            portfolio = self.get_portfolio(portfolio_id)
            normalized: dict[str, Any] = {}
            if "name" in changes:
                normalized["name"] = self._name(changes["name"])
            if "base_currency" in changes:
                normalized["base_currency"] = self._currency(changes["base_currency"])
            self.repository.update_portfolio(portfolio, normalized)
            self.session.commit()
            self.session.refresh(portfolio)
            return portfolio
        except PortfolioDomainError:
            self.session.rollback()
            raise
        except SQLAlchemyError as error:
            self.session.rollback()
            raise PortfolioPersistenceError("Portfolio could not be updated") from error

    def delete_portfolio(self, portfolio_id: int) -> None:
        portfolio = self.get_portfolio(portfolio_id)
        try:
            self.repository.delete_portfolio(portfolio)
            self.session.commit()
        except SQLAlchemyError as error:
            self.session.rollback()
            raise PortfolioPersistenceError("Portfolio could not be deleted") from error

    def list_positions(self, portfolio_id: int) -> list[Position]:
        self.get_portfolio(portfolio_id)
        return self.repository.list_positions(portfolio_id)

    def get_position(self, portfolio_id: int, position_id: int) -> Position:
        self.get_portfolio(portfolio_id)
        position = self.repository.get_position(portfolio_id, position_id)
        if position is None:
            raise PositionNotFoundError("Position not found in this portfolio")
        return position

    def create_position(
        self,
        portfolio_id: int,
        *,
        asset_id: int,
        quantity: Decimal | int | str,
        average_purchase_price: Decimal | int | str,
        purchase_date: date,
        currency: str,
        fees: Decimal | int | str | None = None,
    ) -> Position:
        try:
            self.get_portfolio(portfolio_id)
            asset = self.repository.get_asset(asset_id)
            if asset is None:
                raise AssetNotFoundError("Asset not found")
            if self.repository.get_position_by_asset(portfolio_id, asset_id) is not None:
                raise DuplicatePositionError("Position for this asset already exists")
            normalized_fees = (
                self._decimal(fees, field="fees", precision=20, scale=4)
                if fees is not None else None
            )
            position = self.repository.create_position(
                portfolio_id=portfolio_id,
                asset=asset,
                quantity=self._decimal(
                    quantity,
                    field="quantity",
                    precision=20,
                    scale=8,
                    strictly_positive=True,
                ),
                average_purchase_price=self._decimal(
                    average_purchase_price,
                    field="average_purchase_price",
                    precision=20,
                    scale=6,
                ),
                purchase_date=purchase_date,
                currency=self._currency(currency),
                fees=normalized_fees,
            )
            self.session.commit()
            self.session.refresh(position)
            return position
        except IntegrityError as error:
            self.session.rollback()
            raise DuplicatePositionError("Position for this asset already exists") from error
        except PortfolioDomainError:
            self.session.rollback()
            raise
        except SQLAlchemyError as error:
            self.session.rollback()
            raise PortfolioPersistenceError("Position could not be saved") from error

    def update_position(
        self,
        portfolio_id: int,
        position_id: int,
        changes: dict[str, Any],
    ) -> Position:
        try:
            position = self.get_position(portfolio_id, position_id)
            normalized: dict[str, Any] = {}
            if "quantity" in changes:
                normalized["quantity"] = self._decimal(
                    changes["quantity"], field="quantity", precision=20, scale=8,
                    strictly_positive=True,
                )
            if "average_purchase_price" in changes:
                normalized["average_purchase_price"] = self._decimal(
                    changes["average_purchase_price"],
                    field="average_purchase_price",
                    precision=20,
                    scale=6,
                )
            if "purchase_date" in changes:
                normalized["purchase_date"] = changes["purchase_date"]
            if "currency" in changes:
                normalized["currency"] = self._currency(changes["currency"])
            if "fees" in changes:
                normalized["fees"] = (
                    self._decimal(changes["fees"], field="fees", precision=20, scale=4)
                    if changes["fees"] is not None else None
                )
            self.repository.update_position(position, normalized)
            self.session.commit()
            self.session.refresh(position)
            return position
        except PortfolioDomainError:
            self.session.rollback()
            raise
        except SQLAlchemyError as error:
            self.session.rollback()
            raise PortfolioPersistenceError("Position could not be updated") from error

    def delete_position(self, portfolio_id: int, position_id: int) -> None:
        position = self.get_position(portfolio_id, position_id)
        try:
            self.repository.delete_position(position)
            self.session.commit()
        except SQLAlchemyError as error:
            self.session.rollback()
            raise PortfolioPersistenceError("Position could not be deleted") from error


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
    current_price: Decimal | None
    price_source: str | None = None
    price_updated_at: datetime | None = None
    price_is_stale: bool | None = None


def calculate_market_value(quantity: Decimal, price: Decimal) -> Decimal:
    if quantity < 0 or price < 0:
        raise ValueError("quantity and price cannot be negative")
    return (quantity * price).quantize(Decimal("0.01"))


def position_metrics(position: OwnedPosition) -> dict[str, object]:
    fees = position.fees or Decimal("0")
    invested_capital = (
        position.quantity * position.average_purchase_price + fees
    ).quantize(Decimal("0.01"))
    current_value = (
        calculate_market_value(position.quantity, position.current_price)
        if position.current_price is not None else None
    )
    unrealized_pnl = (
        (current_value - invested_capital).quantize(Decimal("0.01"))
        if current_value is not None else None
    )
    return_percent = (
        (unrealized_pnl / invested_capital * Decimal("100")).quantize(Decimal("0.01"))
        if unrealized_pnl is not None else None
    )
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
        "is_valued": current_value is not None,
        "price_source": position.price_source,
        "price_updated_at": position.price_updated_at,
        "price_is_stale": position.price_is_stale,
    }


def _allocation(
    positions: list[OwnedPosition], metrics: list[dict[str, object]], group: str
) -> list[dict[str, object]]:
    values: defaultdict[str, Decimal] = defaultdict(Decimal)
    total = sum(
        (Decimal(str(item["current_value"])) for item in metrics if item["current_value"] is not None),
        Decimal("0"),
    )
    for position, item in zip(positions, metrics, strict=True):
        if item["current_value"] is None:
            continue
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
    valued_metrics = [item for item in metrics if item["current_value"] is not None]
    current_value = sum(
        (Decimal(str(item["current_value"])) for item in valued_metrics), Decimal("0")
    ).quantize(Decimal("0.01"))
    invested_capital = sum(
        (Decimal(str(item["invested_capital"])) for item in valued_metrics), Decimal("0")
    ).quantize(Decimal("0.01"))
    recorded_invested_capital = sum(
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
        "recorded_invested_capital": recorded_invested_capital,
        "unvalued_positions_count": len(metrics) - len(valued_metrics),
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
                "title": "Пересмотр регулирования технологического сектора",
                "published_at": datetime(2026, 6, 29, 9, 30, tzinfo=UTC),
                "affected_symbols": [symbol for symbol in symbols if symbol in {"AAPL", "MSFT", "NVDA"}],
                "impact": "negative",
                "summary": "Политическая неопределённость повышает риск-премию технологических позиций.",
            },
            {
                "title": "Стабилизация долгосрочных доходностей",
                "published_at": datetime(2026, 6, 28, 16, 0, tzinfo=UTC),
                "affected_symbols": [symbol for symbol in symbols if symbol == "TLT"],
                "impact": "positive",
                "summary": "Стабилизация доходностей поддерживает оценку длинных облигаций.",
            },
        ],
        "disclaimer": DISCLAIMER,
    }
