from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import Asset, Portfolio, Position


class PortfolioRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_portfolios(self) -> list[Portfolio]:
        return list(self.session.scalars(select(Portfolio).order_by(Portfolio.id)))

    def get_portfolio(self, portfolio_id: int) -> Portfolio | None:
        return self.session.scalar(
            select(Portfolio)
            .where(Portfolio.id == portfolio_id)
            .options(
                selectinload(Portfolio.positions).joinedload(Position.asset)
            )
        )

    def create_portfolio(self, *, name: str, base_currency: str) -> Portfolio:
        portfolio = Portfolio(name=name, base_currency=base_currency)
        self.session.add(portfolio)
        self.session.flush()
        return portfolio

    def update_portfolio(
        self,
        portfolio: Portfolio,
        changes: Mapping[str, Any],
    ) -> Portfolio:
        for field, value in changes.items():
            setattr(portfolio, field, value)
        self.session.flush()
        return portfolio

    def delete_portfolio(self, portfolio: Portfolio) -> None:
        self.session.delete(portfolio)
        self.session.flush()

    def list_positions(self, portfolio_id: int) -> list[Position]:
        return list(self.session.scalars(
            select(Position)
            .where(Position.portfolio_id == portfolio_id)
            .options(joinedload(Position.asset))
            .order_by(Position.id)
        ))

    def get_position(self, portfolio_id: int, position_id: int) -> Position | None:
        return self.session.scalar(
            select(Position)
            .where(
                Position.portfolio_id == portfolio_id,
                Position.id == position_id,
            )
            .options(joinedload(Position.asset))
        )

    def get_position_by_asset(self, portfolio_id: int, asset_id: int) -> Position | None:
        return self.session.scalar(
            select(Position).where(
                Position.portfolio_id == portfolio_id,
                Position.asset_id == asset_id,
            )
        )

    def create_position(
        self,
        *,
        portfolio_id: int,
        asset: Asset,
        quantity: Decimal,
        average_purchase_price: Decimal,
        purchase_date: date,
        currency: str,
        fees: Decimal | None,
    ) -> Position:
        position = Position(
            portfolio_id=portfolio_id,
            asset_id=asset.id,
            symbol=asset.symbol,
            quantity=quantity,
            average_purchase_price=average_purchase_price,
            purchase_date=purchase_date,
            currency=currency,
            fees=fees,
        )
        self.session.add(position)
        self.session.flush()
        return position

    def update_position(
        self,
        position: Position,
        changes: Mapping[str, Any],
    ) -> Position:
        for field, value in changes.items():
            setattr(position, field, value)
        self.session.flush()
        return position

    def delete_position(self, position: Position) -> None:
        self.session.delete(position)
        self.session.flush()

    def get_asset(self, asset_id: int) -> Asset | None:
        return self.session.get(Asset, asset_id)

    def get_asset_by_symbol(self, symbol: str) -> Asset | None:
        return self.session.scalar(
            select(Asset).where(Asset.symbol == symbol.upper())
        )
