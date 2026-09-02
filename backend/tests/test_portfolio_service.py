from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base, configure_sqlite_engine, sqlite_database_url
from app.models import Asset, Position
from app.modules.portfolio import (
    AssetNotFoundError,
    DuplicatePositionError,
    PortfolioNotFoundError,
    PortfolioPersistenceError,
    PortfolioService,
    PortfolioValidationError,
    PositionNotFoundError,
)
from app.repositories import PortfolioRepository


def make_asset(
    session: Session,
    *,
    symbol: str = "AAPL",
    name: str = "Apple Inc.",
    currency: str = "USD",
) -> Asset:
    asset = Asset(
        symbol=symbol,
        name=name,
        asset_type="equity",
        exchange="NASDAQ",
        sector="Technology",
        industry="Consumer Electronics",
        currency=currency,
        provider_symbol=symbol,
        is_active=True,
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def create_position(
    service: PortfolioService,
    portfolio_id: int,
    asset_id: int,
    *,
    quantity: Decimal | str = Decimal("2.50000000"),
    price: Decimal | str = Decimal("123.456789"),
) -> Position:
    return service.create_position(
        portfolio_id,
        asset_id=asset_id,
        quantity=quantity,
        average_purchase_price=price,
        purchase_date=date(2024, 1, 15),
        currency="usd",
        fees=Decimal("1.2500"),
    )


def test_empty_portfolio_name_is_rejected(db_session: Session) -> None:
    service = PortfolioService(db_session)

    with pytest.raises(PortfolioValidationError, match="must not be empty"):
        service.create_portfolio(name="   ", base_currency="USD")

    assert service.list_portfolios() == []


def test_portfolio_name_is_trimmed(db_session: Session) -> None:
    portfolio = PortfolioService(db_session).create_portfolio(
        name="  Owned assets  ",
        base_currency="usd",
    )

    assert portfolio.name == "Owned assets"
    assert portfolio.base_currency == "USD"


def test_unknown_portfolio_raises_domain_error(db_session: Session) -> None:
    service = PortfolioService(db_session)

    with pytest.raises(PortfolioNotFoundError):
        service.get_portfolio(999)

    with pytest.raises(PortfolioNotFoundError):
        service.list_positions(999)


def test_unknown_asset_raises_domain_error(db_session: Session) -> None:
    service = PortfolioService(db_session)
    portfolio = service.create_portfolio(name="Owned assets", base_currency="USD")

    with pytest.raises(AssetNotFoundError):
        create_position(service, portfolio.id, 999)


def test_quantity_must_be_positive(db_session: Session) -> None:
    asset = make_asset(db_session)
    service = PortfolioService(db_session)
    portfolio = service.create_portfolio(name="Owned assets", base_currency="USD")

    for value in (Decimal("0"), Decimal("-1")):
        with pytest.raises(PortfolioValidationError, match="quantity"):
            create_position(service, portfolio.id, asset.id, quantity=value)

    assert db_session.scalar(select(func.count()).select_from(Position)) == 0


def test_negative_purchase_price_is_rejected(db_session: Session) -> None:
    asset = make_asset(db_session)
    service = PortfolioService(db_session)
    portfolio = service.create_portfolio(name="Owned assets", base_currency="USD")

    with pytest.raises(PortfolioValidationError, match="average_purchase_price"):
        create_position(service, portfolio.id, asset.id, price=Decimal("-0.01"))

    assert db_session.scalar(select(func.count()).select_from(Position)) == 0


def test_duplicate_position_is_domain_conflict(db_session: Session) -> None:
    asset = make_asset(db_session)
    service = PortfolioService(db_session)
    portfolio = service.create_portfolio(name="Owned assets", base_currency="USD")
    create_position(service, portfolio.id, asset.id)

    with pytest.raises(DuplicatePositionError):
        create_position(service, portfolio.id, asset.id)

    assert db_session.scalar(select(func.count()).select_from(Position)) == 1


def test_position_from_other_portfolio_is_not_updated(db_session: Session) -> None:
    asset = make_asset(db_session)
    service = PortfolioService(db_session)
    first = service.create_portfolio(name="First", base_currency="USD")
    second = service.create_portfolio(name="Second", base_currency="USD")
    position = create_position(service, first.id, asset.id)

    with pytest.raises(PositionNotFoundError):
        service.update_position(second.id, position.id, {"quantity": Decimal("9")})

    restored = service.get_position(first.id, position.id)
    assert restored.quantity == Decimal("2.50000000")


def test_delete_portfolio_deletes_positions(db_session: Session) -> None:
    asset = make_asset(db_session)
    service = PortfolioService(db_session)
    portfolio = service.create_portfolio(name="Owned assets", base_currency="USD")
    create_position(service, portfolio.id, asset.id)

    service.delete_portfolio(portfolio.id)

    assert db_session.scalar(select(func.count()).select_from(Position)) == 0
    with pytest.raises(PortfolioNotFoundError):
        service.get_portfolio(portfolio.id)


class FailingPositionRepository(PortfolioRepository):
    def create_position(self, **kwargs):  # type: ignore[no-untyped-def]
        super().create_position(**kwargs)
        raise SQLAlchemyError("forced failure after partial flush")


def test_rollback_on_error_does_not_keep_partial_position(db_session: Session) -> None:
    asset = make_asset(db_session)
    service = PortfolioService(db_session)
    portfolio = service.create_portfolio(name="Owned assets", base_currency="USD")
    failing_service = PortfolioService(
        db_session,
        repository=FailingPositionRepository(db_session),
    )

    with pytest.raises(PortfolioPersistenceError):
        create_position(failing_service, portfolio.id, asset.id)

    assert db_session.scalar(select(func.count()).select_from(Position)) == 0


def test_money_and_quantity_fields_remain_decimal(db_session: Session) -> None:
    asset = make_asset(db_session)
    service = PortfolioService(db_session)
    portfolio = service.create_portfolio(name="Owned assets", base_currency="USD")

    position = service.create_position(
        portfolio.id,
        asset_id=asset.id,
        quantity=Decimal("0.00000001"),
        average_purchase_price=Decimal("9999999999999.123456"),
        purchase_date=date(2024, 1, 15),
        currency="USD",
        fees=Decimal("265595000000.0000"),
    )

    assert isinstance(position.quantity, Decimal)
    assert isinstance(position.average_purchase_price, Decimal)
    assert isinstance(position.fees, Decimal)
    assert position.quantity == Decimal("0.00000001")
    assert position.average_purchase_price == Decimal("9999999999999.123456")
    assert position.fees == Decimal("265595000000.0000")


def test_decimal_scale_is_validated(db_session: Session) -> None:
    asset = make_asset(db_session)
    service = PortfolioService(db_session)
    portfolio = service.create_portfolio(name="Owned assets", base_currency="USD")

    with pytest.raises(PortfolioValidationError, match="quantity"):
        create_position(service, portfolio.id, asset.id, quantity=Decimal("0.000000001"))

    with pytest.raises(PortfolioValidationError, match="average_purchase_price"):
        create_position(service, portfolio.id, asset.id, price=Decimal("1.0000001"))

    with pytest.raises(PortfolioValidationError, match="fees"):
        service.create_position(
            portfolio.id,
            asset_id=asset.id,
            quantity=Decimal("1"),
            average_purchase_price=Decimal("100"),
            purchase_date=date(2024, 1, 15),
            currency="USD",
            fees=Decimal("1.00001"),
        )

    assert db_session.scalar(select(func.count()).select_from(Position)) == 0


def test_persistence_after_restart_on_file_sqlite_db(tmp_path: Path) -> None:
    database_path = tmp_path / "portfolio-service.db"
    engine = create_engine(sqlite_database_url(database_path))
    configure_sqlite_engine(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    try:
        with factory() as session:
            asset = make_asset(session)
            service = PortfolioService(session)
            portfolio = service.create_portfolio(name="Owned assets", base_currency="USD")
            position = create_position(service, portfolio.id, asset.id)
            portfolio_id = portfolio.id
            position_id = position.id

        engine.dispose()
        engine = create_engine(sqlite_database_url(database_path))
        configure_sqlite_engine(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)

        with factory() as session:
            service = PortfolioService(session)
            restored_portfolio = service.get_portfolio(portfolio_id)
            restored_position = service.get_position(portfolio_id, position_id)

            assert restored_portfolio.name == "Owned assets"
            assert restored_position.asset.symbol == "AAPL"
            assert restored_position.quantity == Decimal("2.50000000")
            assert restored_position.average_purchase_price == Decimal("123.456789")
    finally:
        engine.dispose()
