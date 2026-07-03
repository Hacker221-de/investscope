from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.modules.backtesting import fixed_demo_series, sma_crossover_analysis


client = TestClient(app)


def test_sma_analysis_is_deterministic_and_updates_both_curves() -> None:
    dates, prices = fixed_demo_series(date(2025, 6, 29), date(2026, 6, 29))
    first = sma_crossover_analysis(prices, Decimal("10000"), 10, 30)
    second = sma_crossover_analysis(prices, Decimal("10000"), 10, 30)

    assert first == second
    assert len(first["strategy_curve"]) == len(dates)
    assert len(first["benchmark_curve"]) == len(dates)
    assert first["signals"] == first["correct_signals"] + first["incorrect_signals"]
    assert first["strategy_curve"] != first["benchmark_curve"]


def test_backtesting_endpoint_returns_complete_recalculation() -> None:
    response = client.post("/api/v1/backtesting/run", json={
        "symbol": "AAPL",
        "method": "moving",
        "short_window": 8,
        "long_window": 24,
        "initial_capital": "12500.00",
        "start_date": "2025-06-29",
        "end_date": "2026-06-29",
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "AAPL"
    assert payload["signals"] == payload["correct_signals"] + payload["incorrect_signals"]
    assert len(payload["dates"]) == len(payload["strategy_curve"])
    assert len(payload["dates"]) == len(payload["benchmark_curve"])
    assert payload["final_value"] == payload["strategy_curve"][-1]
    assert payload["benchmark_final_value"] == payload["benchmark_curve"][-1]


def test_backtesting_endpoint_validates_windows_and_dates() -> None:
    invalid_windows = client.post("/api/v1/backtesting/run", json={
        "symbol": "AAPL",
        "short_window": 30,
        "long_window": 10,
        "initial_capital": "10000",
        "start_date": "2025-06-29",
        "end_date": "2026-06-29",
    })
    invalid_dates = client.post("/api/v1/backtesting/run", json={
        "symbol": "AAPL",
        "short_window": 10,
        "long_window": 30,
        "initial_capital": "10000",
        "start_date": "2026-06-29",
        "end_date": "2025-06-29",
    })

    assert invalid_windows.status_code == 422
    assert invalid_dates.status_code == 422
