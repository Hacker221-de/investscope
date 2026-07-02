import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.fundamentals import get_fundamental_provider
from app.core.config import Settings, get_settings
from app.main import app
from app.models import Asset, CompanyFiling, CompanyProfile, FinancialFact
from app.modules.fundamental_analysis.contracts import (
    FundamentalDataProvider,
    ResolvedCompany,
    SecAccessDeniedError,
)
from app.modules.fundamental_analysis.sync import FundamentalSyncService
from app.repositories import FundamentalRepository


def submissions_payload() -> dict:
    return {
        "name": "Apple Inc.",
        "sic": "3571",
        "sicDescription": "Electronic Computers",
        "entityType": "operating",
        "stateOfIncorporation": "CA",
        "fiscalYearEnd": "0927",
        "exchanges": ["Nasdaq"],
        "tickers": ["AAPL"],
        "filings": {"recent": {
            "accessionNumber": ["0000320193-25-000001", "0000320193-25-000002"],
            "filingDate": ["2025-02-01", "2025-02-10"],
            "reportDate": ["2024-12-31", "2024-12-31"],
            "acceptanceDateTime": ["2025-02-01T16:00:00Z", "2025-02-10T17:00:00Z"],
            "form": ["10-K", "10-K/A"],
            "primaryDocument": ["a10-k.htm", "a10-ka.htm"],
            "primaryDocDescription": ["Annual report", "Amended annual report"],
            "fileNumber": ["001-00001", "001-00001"],
            "filmNumber": ["251", "252"],
            "items": ["", ""],
            "isXBRL": [1, 1],
            "isInlineXBRL": [1, 1],
        }},
    }


def companyfacts_payload() -> dict:
    return {"facts": {"us-gaap": {"NetIncomeLoss": {
        "label": "Net income",
        "description": "Net income or loss",
        "units": {"USD": [
            {
                "start": "2024-01-01", "end": "2024-12-31", "val": "100.25",
                "accn": "0000320193-25-000001", "fy": 2024, "fp": "FY",
                "form": "10-K", "filed": "2025-02-01", "frame": "CY2024",
            },
            {
                "start": "2024-01-01", "end": "2024-12-31", "val": "99.75",
                "accn": "0000320193-25-000002", "fy": 2024, "fp": "FY",
                "form": "10-K/A", "filed": "2025-02-10", "frame": "CY2024",
            },
        ]},
    }}}}


class MockSecProvider(FundamentalDataProvider):
    name = "sec_edgar"

    def __init__(self) -> None:
        self.calls: list[str] = []

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        return symbol.strip().upper()

    async def resolve_company(self, symbol: str) -> ResolvedCompany:
        self.calls.append("resolve")
        return ResolvedCompany(
            symbol=symbol.upper(), cik="0000320193", legal_name="Apple Inc.", exchange="Nasdaq"
        )

    async def get_company_profile(self, symbol: str) -> dict:
        self.calls.append("profile")
        return submissions_payload()

    async def get_submissions(self, cik: str) -> dict:
        self.calls.append("submissions")
        return submissions_payload()

    async def get_company_facts(self, cik: str) -> dict:
        self.calls.append("facts")
        return companyfacts_payload()


def test_sync_is_transactional_idempotent_and_preserves_amendments(db_session: Session) -> None:
    provider = MockSecProvider()
    first = asyncio.run(FundamentalSyncService(
        db_session, provider, cache_ttl_hours=0
    ).synchronize("aapl"))
    second = asyncio.run(FundamentalSyncService(
        db_session, provider, cache_ttl_hours=0
    ).synchronize("AAPL"))

    assert first.profile_created == 1
    assert first.filings_inserted == 2
    assert first.facts_inserted == 2
    assert second.profile_updated == 1
    assert second.filings_inserted == 0
    assert second.filings_updated == 2
    assert second.facts_inserted == 0
    assert second.facts_skipped == 2
    assert provider.calls.count("resolve") == 1
    assert db_session.scalar(select(func.count()).select_from(CompanyProfile)) == 1
    assert db_session.scalar(select(func.count()).select_from(CompanyFiling)) == 2
    assert db_session.scalar(select(func.count()).select_from(FinancialFact)) == 2
    forms = list(db_session.scalars(select(CompanyFiling.form).order_by(CompanyFiling.form)))
    assert forms == ["10-K", "10-K/A"]


def test_existing_asset_cik_bypasses_ticker_resolution(db_session: Session) -> None:
    repository = FundamentalRepository(db_session)
    repository.set_known_company(
        symbol="AAPL",
        cik="0000320193",
        legal_name="Apple Inc.",
        exchange="Nasdaq",
    )
    provider = MockSecProvider()

    result = asyncio.run(FundamentalSyncService(
        db_session, provider, cache_ttl_hours=0
    ).synchronize("AAPL"))
    assert result.cik == "0000320193"
    assert "resolve" not in provider.calls
    assert provider.calls == ["submissions", "facts"]


def test_fresh_database_state_skips_all_external_requests(db_session: Session) -> None:
    provider = MockSecProvider()
    first = asyncio.run(FundamentalSyncService(
        db_session, provider, cache_ttl_hours=24
    ).synchronize("AAPL"))
    calls_after_first = list(provider.calls)
    second = asyncio.run(FundamentalSyncService(
        db_session, provider, cache_ttl_hours=24
    ).synchronize("AAPL"))
    assert first.skipped is False
    assert second.skipped is True
    assert second.skip_reason == "fresh_data"
    assert provider.calls == calls_after_first


def test_point_in_time_excludes_filing_and_amendment_until_acceptance(db_session: Session) -> None:
    provider = MockSecProvider()
    asyncio.run(FundamentalSyncService(
        db_session, provider, cache_ttl_hours=0
    ).synchronize("AAPL"))
    repository = FundamentalRepository(db_session)
    asset = repository.get_asset("AAPL")
    assert asset is not None

    before_original = datetime(2025, 2, 1, 12, tzinfo=UTC)
    after_original = datetime(2025, 2, 1, 17, tzinfo=UTC)
    before_amendment = datetime(2025, 2, 10, 12, tzinfo=UTC)
    after_amendment = datetime(2025, 2, 10, 18, tzinfo=UTC)
    assert repository.list_filings(asset_id=asset.id, as_of=before_original) == []
    assert [row.form for row in repository.list_filings(
        asset_id=asset.id, as_of=after_original
    )] == ["10-K"]
    assert [row.form for row in repository.list_filings(
        asset_id=asset.id, as_of=before_amendment
    )] == ["10-K"]
    assert {row.form for row in repository.list_filings(
        asset_id=asset.id, as_of=after_amendment
    )} == {"10-K", "10-K/A"}
    assert repository.list_facts(asset_id=asset.id, as_of=before_original) == []
    assert [row.form for row in repository.list_facts(
        asset_id=asset.id, as_of=after_original
    )] == ["10-K"]
    assert {row.form for row in repository.list_facts(
        asset_id=asset.id, as_of=after_amendment
    )} == {"10-K", "10-K/A"}


def test_sync_rolls_back_if_whole_companyfacts_payload_is_invalid(db_session: Session) -> None:
    provider = MockSecProvider()

    async def invalid_facts(cik: str) -> dict:
        return {"unexpected": True}

    provider.get_company_facts = invalid_facts  # type: ignore[method-assign]
    try:
        asyncio.run(FundamentalSyncService(
            db_session, provider, cache_ttl_hours=0
        ).synchronize("AAPL"))
    except Exception:
        pass
    assert db_session.scalar(select(func.count()).select_from(Asset)) == 0


def test_fundamentals_api_sync_filters_and_does_not_expose_user_agent(
    market_client: TestClient,
) -> None:
    provider = MockSecProvider()
    app.dependency_overrides[get_fundamental_provider] = lambda: provider
    app.dependency_overrides[get_settings] = lambda: Settings(
        sec_user_agent="InvestScope private-contact@example.com",
        sec_cache_ttl_hours=0,
    )
    try:
        sync = market_client.post("/api/fundamentals/aapl/sync")
        assert sync.status_code == 200
        assert sync.json()["facts_inserted"] == 2
        profile = market_client.get("/api/fundamentals/AAPL/profile")
        assert profile.status_code == 200
        assert profile.json()["cik"] == "0000320193"
        filings = market_client.get(
            "/api/fundamentals/AAPL/filings", params={"form": "10-K/A"}
        )
        assert [row["form"] for row in filings.json()] == ["10-K/A"]
        facts = market_client.get(
            "/api/fundamentals/AAPL/facts",
            params={"metric": "net_income", "fiscal_year": 2024},
        )
        assert len(facts.json()) == 2
        serialized = sync.text + profile.text + filings.text + facts.text
        assert "private-contact" not in serialized
        assert "sec_user_agent" not in serialized
    finally:
        app.dependency_overrides.pop(get_fundamental_provider, None)
        app.dependency_overrides.pop(get_settings, None)


def test_fundamentals_api_returns_stable_sec_error(market_client: TestClient) -> None:
    provider = MockSecProvider()

    async def denied(symbol: str) -> ResolvedCompany:
        raise SecAccessDeniedError("raw SEC body and private contact")

    provider.resolve_company = denied  # type: ignore[method-assign]
    app.dependency_overrides[get_fundamental_provider] = lambda: provider
    try:
        response = market_client.post("/api/fundamentals/AAPL/sync")
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "sec_access_denied"
        assert "raw SEC body" not in response.text
        assert "private contact" not in response.text
    finally:
        app.dependency_overrides.pop(get_fundamental_provider, None)


def test_fundamentals_api_returns_stale_ticker_cache_warning(
    market_client: TestClient,
) -> None:
    provider = MockSecProvider()

    async def stale_company(symbol: str) -> ResolvedCompany:
        return ResolvedCompany(
            symbol="AAPL",
            cik="0000320193",
            legal_name="Apple Inc.",
            exchange="Nasdaq",
            warning="sec_ticker_cache_stale",
        )

    provider.resolve_company = stale_company  # type: ignore[method-assign]
    app.dependency_overrides[get_fundamental_provider] = lambda: provider
    try:
        response = market_client.post("/api/fundamentals/AAPL/sync")
        assert response.status_code == 200
        assert response.json()["warning"] == "sec_ticker_cache_stale"
    finally:
        app.dependency_overrides.pop(get_fundamental_provider, None)


def test_fundamentals_api_rejects_non_ascii_ticker(market_client: TestClient) -> None:
    response = market_client.post("/api/fundamentals/ААПЛ/sync")
    assert response.status_code == 422
