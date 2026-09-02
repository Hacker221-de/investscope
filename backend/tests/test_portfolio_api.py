from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Asset
from app.modules.data_sources import ProviderMarketBar, Timeframe
from app.repositories import MarketDataRepository, PortfolioRepository


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


def create_portfolio(client: TestClient, *, name: str = "Owned assets") -> dict[str, object]:
    response = client.post(
        "/api/v1/portfolios",
        json={"name": name, "base_currency": "usd"},
    )
    assert response.status_code == 201
    return response.json()


def create_position(
    client: TestClient,
    portfolio_id: int,
    asset_id: int,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions",
        json={
            "asset_id": asset_id,
            "quantity": "2.50000000",
            "average_purchase_price": "123.456789",
            "purchase_date": "2024-01-15",
            "currency": "usd",
            "fees": "1.2500",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_get_portfolios_returns_empty_list(market_client: TestClient) -> None:
    response = market_client.get("/api/v1/portfolios")

    assert response.status_code == 200
    assert response.json() == []


def test_portfolio_crud(market_client: TestClient) -> None:
    created = create_portfolio(market_client, name="  Owned assets  ")
    portfolio_id = int(created["id"])

    assert created["name"] == "Owned assets"
    assert created["base_currency"] == "USD"
    assert isinstance(created["created_at"], str)

    detail_response = market_client.get(f"/api/v1/portfolios/{portfolio_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == portfolio_id
    assert detail["positions"] == []

    patch_response = market_client.patch(
        f"/api/v1/portfolios/{portfolio_id}",
        json={"name": "Long-term holdings", "base_currency": "eur"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Long-term holdings"
    assert patch_response.json()["base_currency"] == "EUR"

    delete_response = market_client.delete(f"/api/v1/portfolios/{portfolio_id}")
    assert delete_response.status_code == 204
    assert delete_response.text == ""
    assert market_client.get(f"/api/v1/portfolios/{portfolio_id}").status_code == 404


def test_position_crud_and_decimal_serialization(
    market_client: TestClient,
    db_session: Session,
) -> None:
    asset = make_asset(db_session)
    portfolio_id = int(create_portfolio(market_client)["id"])

    created = create_position(market_client, portfolio_id, asset.id)
    position_id = int(created["id"])

    assert created["portfolio_id"] == portfolio_id
    assert created["asset_id"] == asset.id
    assert created["symbol"] == "AAPL"
    assert created["quantity"] == "2.50000000"
    assert created["average_purchase_price"] == "123.456789"
    assert created["fees"] == "1.2500"
    assert created["currency"] == "USD"
    assert created["purchase_date"] == "2024-01-15"

    list_response = market_client.get(f"/api/v1/portfolios/{portfolio_id}/positions")
    assert list_response.status_code == 200
    assert [position["id"] for position in list_response.json()] == [position_id]

    get_response = market_client.get(
        f"/api/v1/portfolios/{portfolio_id}/positions/{position_id}"
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == position_id

    patch_response = market_client.patch(
        f"/api/v1/portfolios/{portfolio_id}/positions/{position_id}",
        json={
            "quantity": "3.75000000",
            "average_purchase_price": "120.000001",
            "fees": None,
        },
    )
    assert patch_response.status_code == 200
    updated = patch_response.json()
    assert updated["quantity"] == "3.75000000"
    assert updated["average_purchase_price"] == "120.000001"
    assert updated["fees"] is None

    delete_response = market_client.delete(
        f"/api/v1/portfolios/{portfolio_id}/positions/{position_id}"
    )
    assert delete_response.status_code == 204
    assert market_client.get(
        f"/api/v1/portfolios/{portfolio_id}/positions/{position_id}"
    ).status_code == 404


def test_duplicate_position_returns_409(
    market_client: TestClient,
    db_session: Session,
) -> None:
    asset = make_asset(db_session)
    portfolio_id = int(create_portfolio(market_client)["id"])
    create_position(market_client, portfolio_id, asset.id)

    response = market_client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions",
        json={
            "asset_id": asset.id,
            "quantity": "1",
            "average_purchase_price": "100",
            "purchase_date": "2024-01-15",
            "currency": "USD",
        },
    )

    assert response.status_code == 409
    assert "Position for this asset already exists" in response.json()["detail"]
    assert "Traceback" not in response.text


def test_unknown_asset_returns_404(market_client: TestClient) -> None:
    portfolio_id = int(create_portfolio(market_client)["id"])

    response = market_client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions",
        json={
            "asset_id": 999,
            "quantity": "1",
            "average_purchase_price": "100",
            "purchase_date": "2024-01-15",
            "currency": "USD",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Asset not found"
    assert "Traceback" not in response.text


def test_unknown_portfolio_returns_404(market_client: TestClient) -> None:
    response = market_client.get("/api/v1/portfolios/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio not found"
    assert "Traceback" not in response.text


def test_unknown_position_returns_404(
    market_client: TestClient,
    db_session: Session,
) -> None:
    make_asset(db_session)
    portfolio_id = int(create_portfolio(market_client)["id"])

    response = market_client.get(f"/api/v1/portfolios/{portfolio_id}/positions/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Position not found in this portfolio"
    assert "Traceback" not in response.text


def test_position_is_not_accessible_through_another_portfolio_id(
    market_client: TestClient,
    db_session: Session,
) -> None:
    asset = make_asset(db_session)
    first_id = int(create_portfolio(market_client, name="First")["id"])
    second_id = int(create_portfolio(market_client, name="Second")["id"])
    position_id = int(create_position(market_client, first_id, asset.id)["id"])

    response = market_client.get(
        f"/api/v1/portfolios/{second_id}/positions/{position_id}"
    )
    patch_response = market_client.patch(
        f"/api/v1/portfolios/{second_id}/positions/{position_id}",
        json={"quantity": "9"},
    )

    assert response.status_code == 404
    assert patch_response.status_code == 404
    assert "Traceback" not in response.text
    assert "Traceback" not in patch_response.text


def test_invalid_payload_does_not_return_traceback(market_client: TestClient) -> None:
    response = market_client.post(
        "/api/v1/portfolios",
        json={"name": "Owned assets", "base_currency": "US1"},
    )

    assert response.status_code == 422
    assert "Traceback" not in response.text


def test_legacy_portfolio_endpoint_reads_database(
    market_client: TestClient,
    db_session: Session,
) -> None:
    asset = make_asset(db_session)
    repository = MarketDataRepository(db_session)
    repository.upsert_bars(asset.id, [
        ProviderMarketBar(
            timeframe=Timeframe.DAY_1,
            event_time=datetime(2026, 6, 29, tzinfo=UTC),
            close=Decimal("200"),
            provider="demo",
            received_at=datetime(2026, 6, 29, 23, tzinfo=UTC),
        )
    ])
    db_session.commit()

    portfolio_id = int(create_portfolio(market_client)["id"])
    create_position(market_client, portfolio_id, asset.id)

    response = market_client.get("/api/v1/portfolio")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Owned assets"
    assert payload["positions"][0]["symbol"] == "AAPL"
    assert payload["positions"][0]["current_price"] == "200.00000000"
    assert payload["positions"][0]["is_valued"] is True
    assert "paper" not in payload["disclaimer"].lower()


def test_legacy_position_create_writes_same_database(
    market_client: TestClient,
    db_session: Session,
) -> None:
    asset = make_asset(db_session, symbol="MSFT", name="Microsoft Corp.")
    portfolio = PortfolioRepository(db_session).create_portfolio(
        name="Owned assets",
        base_currency="USD",
    )
    db_session.commit()

    response = market_client.post(
        "/api/v1/portfolio/positions",
        json={
            "symbol": "msft",
            "quantity": "1.25",
            "average_purchase_price": "300.00",
            "purchase_date": "2024-01-15",
            "currency": "usd",
            "fees": "0.50",
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["symbol"] == "MSFT"
    assert created["quantity"] == "1.25000000"
    assert PortfolioRepository(db_session).get_position_by_asset(
        portfolio.id,
        asset.id,
    ) is not None
