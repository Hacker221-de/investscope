import json
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from starlette.requests import Request

from app.api.fundamentals import get_fundamental_provider
from app.api.market_data import get_market_data_provider
from app.core.config import get_settings
from app.core.database import get_db
from app.main import create_app
from app.models import Asset, CompanyFiling, CompanyProfile, FinancialFact, MarketBar, Portfolio, Position
from app.modules.data_sources import DemoMarketDataProvider
from app.modules.portfolio import PortfolioService
from test_fundamental_sync_api import MockSecProvider
from test_request_security import LOCAL_ORIGIN, REMOTE_ORIGIN, call_http, security_settings


def database_counts(session):
    return tuple(session.scalar(select(func.count()).select_from(model)) for model in (
        Asset, Portfolio, Position, CompanyProfile, CompanyFiling, FinancialFact, MarketBar,
    ))


@pytest.fixture
def secured_app(db_session, monkeypatch):
    settings = security_settings(market_data_provider="demo")
    application = create_app(settings)
    application.state.db_calls = 0
    def database():
        application.state.db_calls += 1
        yield db_session
    application.dependency_overrides[get_db] = database
    # This is endpoint/service config only; middleware got its own constructor config.
    application.dependency_overrides[get_settings] = lambda: settings
    def no_network(*args, **kwargs):
        pytest.fail("Security tests must never call real providers")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_network)
    return application


@pytest.fixture
def secured_client(secured_app):
    with TestClient(secured_app, base_url="http://127.0.0.1") as client:
        yield client


@pytest.mark.parametrize("path", ["/api/assets", "/api/v1/portfolios", "/health", "/openapi.json"])
def test_dns_rebinding_get_rejected_without_db_access(secured_app, db_session, path):
    before = database_counts(db_session)
    status, body, received, _ = call_http(secured_app, path=path, headers=[("host", "evil.example")])
    assert status == 403 and json.loads(body) == {"detail": "Forbidden request host"}
    assert received == secured_app.state.db_calls == 0
    assert database_counts(db_session) == before


@pytest.mark.parametrize("origin", [None, LOCAL_ORIGIN])
def test_portfolio_csrf_no_content_type_and_positive_control(secured_app, db_session, origin):
    body = b'{"name":"CSRF-TEST"}'
    before = database_counts(db_session)
    attack = call_http(secured_app, method="POST", path="/api/v1/portfolios", body=body,
                       headers=[("host", "127.0.0.1"), ("origin", "https://evil.example")])
    assert attack[0] == 403 and attack[2] == secured_app.state.db_calls == 0
    assert database_counts(db_session) == before
    headers = [("host", "127.0.0.1")]
    if origin:
        headers.append(("origin", origin))
    control = call_http(secured_app, method="POST", path="/api/v1/portfolios", body=body, headers=headers)
    # FastAPI 0.138 has strict_content_type=True; do not change the existing parser.
    assert control[0] == 422 and control[2] == 1
    assert database_counts(db_session) == before
    headers.append(("content-type", "application/json"))
    control = call_http(secured_app, method="POST", path="/api/v1/portfolios", body=body, headers=headers)
    assert control[0] == 201 and control[2] == 1
    assert db_session.scalar(select(Portfolio)).name == "CSRF-TEST"


@pytest.mark.parametrize("origin", [None, LOCAL_ORIGIN])
def test_position_csrf_no_content_type_and_positive_control(secured_app, db_session, origin):
    portfolio = PortfolioService(db_session).create_portfolio(name="Owned", base_currency="USD")
    asset = Asset(symbol="AAPL", name="Apple", asset_type="Equity", currency="USD")
    db_session.add(asset)
    db_session.commit()
    path = f"/api/v1/portfolios/{portfolio.id}/positions"
    body = json.dumps({"asset_id": asset.id, "quantity": "2", "average_purchase_price": "10.5",
                       "purchase_date": "2024-01-15", "currency": "USD"}).encode()
    before = database_counts(db_session)
    attack = call_http(secured_app, method="POST", path=path, body=body,
                       headers=[("host", "127.0.0.1"), ("origin", "https://evil.example")])
    assert attack[0] == 403 and attack[2] == secured_app.state.db_calls == 0
    assert database_counts(db_session) == before
    headers = [("host", "127.0.0.1")]
    if origin:
        headers.append(("origin", origin))
    control = call_http(secured_app, method="POST", path=path, body=body, headers=headers)
    assert control[0] == 422 and control[2] == 1
    assert database_counts(db_session) == before
    headers.append(("content-type", "application/json"))
    control = call_http(secured_app, method="POST", path=path, body=body, headers=headers)
    assert control[0] == 201 and control[2] == 1
    assert db_session.scalar(select(func.count()).select_from(Position)) == 1


def test_legacy_csv_rejected_before_fastapi_file_dependency(secured_app, db_session, monkeypatch):
    before = database_counts(db_session)
    def forbidden(*args, **kwargs):
        pytest.fail("Rejected CSV reached body/parser/service")
    monkeypatch.setattr(Request, "body", forbidden)
    monkeypatch.setattr(Request, "json", forbidden)
    monkeypatch.setattr(Request, "form", forbidden)
    monkeypatch.setattr(PortfolioService, "create_position", forbidden)
    result = call_http(secured_app, method="POST", path="/api/v1/portfolio/import-csv",
                       headers=[("host", "127.0.0.1"), ("origin", "https://evil.example"),
                                ("content-type", "multipart/form-data; boundary=upload")],
                       body=b'--upload\r\nContent-Disposition: form-data; name="file"; filename="owned.csv"\r\n\r\n')
    assert result[0] == 403 and result[2] == secured_app.state.db_calls == 0
    assert database_counts(db_session) == before


def test_legacy_csv_positive_control_is_unchanged(secured_client, db_session):
    PortfolioService(db_session).create_portfolio(name="Owned", base_currency="USD")
    db_session.add(Asset(symbol="AAPL", name="Apple", asset_type="Equity", currency="USD"))
    db_session.commit()
    response = secured_client.post("/api/v1/portfolio/import-csv", headers={"origin": LOCAL_ORIGIN}, files={
        "file": ("owned.csv", b"symbol,quantity,average_purchase_price,purchase_date,currency\nAAPL,2,10.5,2024-01-15,USD\n"),
    })
    assert response.status_code == 200
    assert db_session.scalar(select(func.count()).select_from(Position)) == 1


class CountingMarketProvider(DemoMarketDataProvider):
    def __init__(self):
        self.calls = []
    async def get_asset_metadata(self, symbol):
        self.calls.append("metadata")
        return await super().get_asset_metadata(symbol)
    async def get_historical_bars(self, *args, **kwargs):
        self.calls.append("history")
        return await super().get_historical_bars(*args, **kwargs)
    async def get_latest_bar(self, symbol):
        self.calls.append("latest")
        return await super().get_latest_bar(symbol)


@pytest.mark.parametrize("provider_type", ["sec", "market"])
@pytest.mark.parametrize("origin", [None, LOCAL_ORIGIN])
def test_sync_provider_not_called_for_attack_but_controls_work(secured_app, db_session, provider_type, origin):
    if provider_type == "sec":
        provider, dependency, path, query = MockSecProvider(), get_fundamental_provider, "/api/fundamentals/AAPL/sync", b""
    else:
        provider, dependency, path, query = CountingMarketProvider(), get_market_data_provider, "/api/market/AAPL/sync", b"start=2026-06-01&end=2026-06-10"
    constructions = []
    def get_provider():
        constructions.append(True)
        return provider
    secured_app.dependency_overrides[dependency] = get_provider
    before = database_counts(db_session)
    attack = call_http(secured_app, method="POST", path=path, query=query, headers=[
        ("host", "127.0.0.1"), ("origin", "https://evil.example"),
    ])
    assert attack[0] == 403 and attack[2] == secured_app.state.db_calls == 0
    assert not constructions and not provider.calls
    assert database_counts(db_session) == before
    headers = [("host", "127.0.0.1")]
    if origin:
        headers.append(("origin", origin))
    control = call_http(secured_app, method="POST", path=path, query=query, headers=headers)
    assert control[0] == 200, control[1]
    assert constructions and provider.calls


@pytest.mark.parametrize(("method", "path"), [
    ("PATCH", "/api/v1/portfolios/1"), ("DELETE", "/api/v1/portfolios/1"),
    ("PATCH", "/api/v1/portfolios/1/positions/1"), ("DELETE", "/api/v1/portfolios/1/positions/1"),
    ("POST", "/api/v1/portfolio/positions"), ("PATCH", "/api/v1/portfolio/positions/1"),
    ("DELETE", "/api/v1/portfolio/positions/1"), ("CUSTOM", "/route-that-does-not-exist"),
])
def test_crud_and_legacy_routes_protected_before_validation(secured_app, db_session, method, path):
    portfolio = PortfolioService(db_session).create_portfolio(name="Do not modify", base_currency="USD")
    before = database_counts(db_session)
    result = call_http(secured_app, method=method, path=path, body=b'{"name":"Changed"}', headers=[
        ("host", "127.0.0.1"), ("origin", "https://evil.example"),
    ])
    assert result[0] == 403 and result[2] == secured_app.state.db_calls == 0
    assert database_counts(db_session) == before
    db_session.refresh(portfolio)
    assert portfolio.name == "Do not modify"


def test_backtesting_attack_does_not_invoke_calculation(secured_app, monkeypatch):
    calculation = Mock(side_effect=AssertionError("Calculation must not run"))
    monkeypatch.setattr("app.api.router.sma_crossover_analysis", calculation)
    result = call_http(secured_app, method="POST", path="/api/v1/backtesting/run", body=b"{}", headers=[
        ("host", "127.0.0.1"), ("origin", "https://evil.example"),
    ])
    assert result[0] == 403 and result[2] == 0
    calculation.assert_not_called()


@pytest.mark.parametrize(("host", "origin"), [
    ("api.example.test", None), ("localhost", REMOTE_ORIGIN),
])
def test_sec_upload_retains_stricter_loopback_policy(host, origin, db_session, monkeypatch):
    settings = security_settings(trusted_hosts=["api.example.test"], cors_origins=[REMOTE_ORIGIN])
    application = create_app(settings)
    application.dependency_overrides[get_db] = lambda: db_session
    application.dependency_overrides[get_settings] = lambda: settings
    def forbidden(*args, **kwargs):
        pytest.fail("SEC upload accepted remote request past its stricter guard")
    monkeypatch.setattr(Request, "form", forbidden)
    headers = [("host", host)]
    if origin:
        headers.append(("origin", origin))
    # Global server policy permits these requests; endpoint-specific guard must reject.
    status, body, received, _ = call_http(application, method="POST", path="/api/fundamentals/AAPL/import-json", headers=headers)
    assert status == 403 and received == 0
    assert "loopback" in json.loads(body)["detail"]
