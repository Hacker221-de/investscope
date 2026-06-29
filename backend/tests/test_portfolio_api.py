from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_portfolio_contains_full_analytics_and_disclaimer() -> None:
    response = client.get("/api/v1/portfolio")

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_value"] == "87879.58"
    assert payload["invested_capital"] == "80200.00"
    assert payload["unrealized_pnl"] == "7679.58"
    assert payload["allocation_by_asset"]
    assert payload["allocation_by_sector"]
    assert payload["allocation_by_currency"]
    assert payload["risk"]["historical_volatility_percent"] == "21.40"
    assert payload["risk"]["max_drawdown_percent"] == "4.63"
    assert payload["correlations"]
    assert payload["political_and_geographic_risks"]
    assert payload["stress_scenarios"]
    assert payload["news_impacts"]
    assert "не подключается к брокеру" in payload["disclaimer"]


def test_manual_position_crud() -> None:
    create_response = client.post(
        "/api/v1/portfolio/positions",
        json={
            "symbol": "NVDA",
            "quantity": "3.5",
            "average_purchase_price": "140.25",
            "purchase_date": "2025-05-10",
            "currency": "usd",
            "fees": "4.50",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["symbol"] == "NVDA"
    assert created["currency"] == "USD"
    assert created["fees"] == "4.50"

    position_id = created["id"]
    update_response = client.patch(
        f"/api/v1/portfolio/positions/{position_id}",
        json={"quantity": "4.25", "average_purchase_price": "142.00"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["quantity"] == "4.25"

    delete_response = client.delete(f"/api/v1/portfolio/positions/{position_id}")
    assert delete_response.status_code == 204
    assert client.patch(f"/api/v1/portfolio/positions/{position_id}", json={"quantity": "1"}).status_code == 404


def test_csv_import() -> None:
    csv_body = (
        "symbol,quantity,average_purchase_price,purchase_date,currency,fees\n"
        "NVDA,2,145.50,2025-04-20,USD,3.25\n"
    )
    response = client.post(
        "/api/v1/portfolio/import-csv",
        files={"file": ("positions.csv", csv_body, "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["imported_count"] == 1
    assert payload["errors"] == []
    position_id = payload["positions"][0]["id"]
    assert client.delete(f"/api/v1/portfolio/positions/{position_id}").status_code == 204


def test_unknown_symbol_is_rejected_for_analysis() -> None:
    response = client.post(
        "/api/v1/portfolio/positions",
        json={
            "symbol": "UNKNOWN",
            "quantity": "1",
            "average_purchase_price": "10",
            "purchase_date": "2025-01-01",
            "currency": "USD",
        },
    )

    assert response.status_code == 422
