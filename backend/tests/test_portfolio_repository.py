from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base, configure_sqlite_engine, sqlite_database_url
from app.models import Asset, Portfolio, Position
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
    session.flush()
    return asset


def test_list_portfolios_is_empty_for_new_database(db_session: Session) -> None:
    assert PortfolioRepository(db_session).list_portfolios() == []


def test_create_get_update_and_delete_portfolio(db_session: Session) -> None:
    repository = PortfolioRepository(db_session)

    portfolio = repository.create_portfolio(name="Owned assets", base_currency="USD")
    db_session.commit()

    assert portfolio.id is not None
    assert repository.get_portfolio(portfolio.id) == portfolio

    repository.update_portfolio(portfolio, {"name": "Long-term holdings", "base_currency": "EUR"})
    db_session.commit()

    restored = repository.get_portfolio(portfolio.id)
    assert restored is not None
    assert restored.name == "Long-term holdings"
    assert restored.base_currency == "EUR"

    repository.delete_portfolio(restored)
    db_session.commit()

    assert repository.get_portfolio(portfolio.id) is None
    assert repository.list_portfolios() == []


def test_create_get_update_and_delete_position(db_session: Session) -> None:
    repository = PortfolioRepository(db_session)
    asset = make_asset(db_session)
    portfolio = repository.create_portfolio(name="Owned assets", base_currency="USD")

    position = repository.create_position(
        portfolio_id=portfolio.id,
        asset=asset,
        quantity=Decimal("2.50000000"),
        average_purchase_price=Decimal("123.456789"),
        purchase_date=date(2024, 1, 15),
        currency="USD",
        fees=Decimal("1.2500"),
    )
    db_session.commit()

    restored = repository.get_position(portfolio.id, position.id)
    assert restored is not None
    assert restored.asset_id == asset.id
    assert restored.asset.symbol == "AAPL"
    assert restored.quantity == Decimal("2.50000000")
    assert restored.average_purchase_price == Decimal("123.456789")
    assert restored.fees == Decimal("1.2500")

    repository.update_position(
        restored,
        {
            "quantity": Decimal("3.75000000"),
            "average_purchase_price": Decimal("120.000001"),
            "fees": None,
        },
    )
    db_session.commit()

    updated = repository.get_position(portfolio.id, position.id)
    assert updated is not None
    assert updated.quantity == Decimal("3.75000000")
    assert updated.average_purchase_price == Decimal("120.000001")
    assert updated.fees is None

    repository.delete_position(updated)
    db_session.commit()

    assert repository.get_position(portfolio.id, position.id) is None
    assert repository.list_positions(portfolio.id) == []


def test_deleting_portfolio_cascades_positions(db_session: Session) -> None:
    repository = PortfolioRepository(db_session)
    asset = make_asset(db_session)
    portfolio = repository.create_portfolio(name="Owned assets", base_currency="USD")
    repository.create_position(
        portfolio_id=portfolio.id,
        asset=asset,
        quantity=Decimal("1"),
        average_purchase_price=Decimal("100"),
        purchase_date=date(2024, 1, 1),
        currency="USD",
        fees=None,
    )
    db_session.commit()

    repository.delete_portfolio(portfolio)
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Portfolio)) == 0
    assert db_session.scalar(select(func.count()).select_from(Position)) == 0


def test_duplicate_asset_inside_one_portfolio_is_rejected(db_session: Session) -> None:
    repository = PortfolioRepository(db_session)
    asset = make_asset(db_session)
    portfolio = repository.create_portfolio(name="Owned assets", base_currency="USD")
    kwargs = {
        "portfolio_id": portfolio.id,
        "asset": asset,
        "quantity": Decimal("1"),
        "average_purchase_price": Decimal("100"),
        "purchase_date": date(2024, 1, 1),
        "currency": "USD",
        "fees": None,
    }
    repository.create_position(**kwargs)
    db_session.commit()

    with pytest.raises(IntegrityError):
        repository.create_position(**kwargs)

    db_session.rollback()
    assert len(repository.list_positions(portfolio.id)) == 1


def test_same_asset_can_exist_once_per_portfolio(db_session: Session) -> None:
    repository = PortfolioRepository(db_session)
    asset = make_asset(db_session)
    first = repository.create_portfolio(name="First", base_currency="USD")
    second = repository.create_portfolio(name="Second", base_currency="USD")

    for portfolio in (first, second):
        repository.create_position(
            portfolio_id=portfolio.id,
            asset=asset,
            quantity=Decimal("1"),
            average_purchase_price=Decimal("100"),
            purchase_date=date(2024, 1, 1),
            currency="USD",
            fees=None,
        )
    db_session.commit()

    assert len(repository.list_positions(first.id)) == 1
    assert len(repository.list_positions(second.id)) == 1
    assert db_session.scalar(select(func.count()).select_from(Position)) == 2


def test_repository_returns_deterministic_order(db_session: Session) -> None:
    repository = PortfolioRepository(db_session)
    second_portfolio = repository.create_portfolio(name="Second", base_currency="USD")
    first_portfolio = repository.create_portfolio(name="First", base_currency="USD")
    first_asset = make_asset(db_session, symbol="MSFT", name="Microsoft Corp.")
    second_asset = make_asset(db_session, symbol="AAPL", name="Apple Inc.")

    second_position = repository.create_position(
        portfolio_id=first_portfolio.id,
        asset=second_asset,
        quantity=Decimal("1"),
        average_purchase_price=Decimal("100"),
        purchase_date=date(2024, 1, 1),
        currency="USD",
        fees=None,
    )
    first_position = repository.create_position(
        portfolio_id=first_portfolio.id,
        asset=first_asset,
        quantity=Decimal("1"),
        average_purchase_price=Decimal("100"),
        purchase_date=date(2024, 1, 1),
        currency="USD",
        fees=None,
    )
    db_session.commit()

    assert [portfolio.id for portfolio in repository.list_portfolios()] == [
        second_portfolio.id,
        first_portfolio.id,
    ]
    assert [position.id for position in repository.list_positions(first_portfolio.id)] == [
        second_position.id,
        first_position.id,
    ]


def test_decimal_values_are_stored_exactly(db_session: Session) -> None:
    repository = PortfolioRepository(db_session)
    asset = make_asset(db_session)
    portfolio = repository.create_portfolio(name="Owned assets", base_currency="USD")

    position = repository.create_position(
        portfolio_id=portfolio.id,
        asset=asset,
        quantity=Decimal("0.00000001"),
        average_purchase_price=Decimal("9999999999999.123456"),
        purchase_date=date(2024, 1, 1),
        currency="USD",
        fees=Decimal("265595000000.0000"),
    )
    db_session.commit()
    db_session.expire_all()

    restored = repository.get_position(portfolio.id, position.id)
    assert restored is not None
    assert isinstance(restored.quantity, Decimal)
    assert isinstance(restored.average_purchase_price, Decimal)
    assert isinstance(restored.fees, Decimal)
    assert restored.quantity == Decimal("0.00000001")
    assert restored.average_purchase_price == Decimal("9999999999999.123456")
    assert restored.fees == Decimal("265595000000.0000")


def test_data_is_read_after_session_reopen(tmp_path: Path) -> None:
    database_path = tmp_path / "portfolio-repository.db"
    engine = create_engine(sqlite_database_url(database_path))
    configure_sqlite_engine(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    try:
        with factory() as session:
            repository = PortfolioRepository(session)
            asset = make_asset(session)
            portfolio = repository.create_portfolio(name="Owned assets", base_currency="USD")
            position = repository.create_position(
                portfolio_id=portfolio.id,
                asset=asset,
                quantity=Decimal("3.25000000"),
                average_purchase_price=Decimal("150.250000"),
                purchase_date=date(2024, 2, 1),
                currency="USD",
                fees=Decimal("2.0000"),
            )
            session.commit()
            portfolio_id = portfolio.id
            position_id = position.id

        with factory() as session:
            repository = PortfolioRepository(session)
            restored_portfolio = repository.get_portfolio(portfolio_id)
            restored_position = repository.get_position(portfolio_id, position_id)

            assert restored_portfolio is not None
            assert restored_portfolio.name == "Owned assets"
            assert restored_position is not None
            assert restored_position.asset.symbol == "AAPL"
            assert restored_position.quantity == Decimal("3.25000000")
    finally:
        engine.dispose()
