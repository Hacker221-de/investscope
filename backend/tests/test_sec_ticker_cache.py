import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.modules.fundamental_analysis.contracts import ResolvedCompany, SecRateLimitError
from app.modules.fundamental_analysis.sec_provider import SecEdgarFundamentalDataProvider
from app.repositories import FundamentalRepository


class TickerIndexGateway:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    async def get_ticker_index(self) -> dict:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [
                [320193, "Apple Inc.", "AAPL", "Nasdaq"],
                [789019, "Microsoft Corp.", "MSFT", "Nasdaq"],
            ],
        }


def test_company_resolution_survives_provider_restart_via_persistent_cache(
    db_session: Session,
) -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=UTC)
    repository = FundamentalRepository(db_session)
    first_gateway = TickerIndexGateway()
    first_provider = SecEdgarFundamentalDataProvider(
        first_gateway,  # type: ignore[arg-type]
        ticker_cache=repository,
        ticker_cache_ttl_hours=168,
        now=lambda: now,
    )
    first = asyncio.run(first_provider.resolve_company("AAPL"))
    assert first_gateway.calls == 1
    assert first.cik == "0000320193"

    db_session.expire_all()
    restarted_gateway = TickerIndexGateway(error=AssertionError("ticker index must not run"))
    restarted_provider = SecEdgarFundamentalDataProvider(
        restarted_gateway,  # type: ignore[arg-type]
        ticker_cache=FundamentalRepository(db_session),
        ticker_cache_ttl_hours=168,
        now=lambda: now + timedelta(hours=1),
    )
    second = asyncio.run(restarted_provider.resolve_company("AAPL"))
    assert second == first
    assert restarted_gateway.calls == 0


def test_stale_persistent_cache_is_used_when_sec_rate_limits_ticker_index(
    db_session: Session,
) -> None:
    now = datetime(2026, 7, 2, 12, tzinfo=UTC)
    repository = FundamentalRepository(db_session)
    repository.store_cached_companies(
        [ResolvedCompany(
            symbol="AAPL", cik="0000320193", legal_name="Apple Inc.", exchange="Nasdaq"
        )],
        fetched_at=now - timedelta(days=8),
    )
    gateway = TickerIndexGateway(error=SecRateLimitError("rate threshold"))
    provider = SecEdgarFundamentalDataProvider(
        gateway,  # type: ignore[arg-type]
        ticker_cache=repository,
        ticker_cache_ttl_hours=168,
        now=lambda: now,
    )

    company = asyncio.run(provider.resolve_company("AAPL"))
    assert company.cik == "0000320193"
    assert company.warning == "sec_ticker_cache_stale"
    assert gateway.calls == 1


def test_bootstrap_rejects_conflicting_cik(db_session: Session) -> None:
    repository = FundamentalRepository(db_session)
    asset = repository.set_known_company(
        symbol="aapl",
        cik="0000320193",
        legal_name="Apple Inc.",
        exchange="Nasdaq",
    )
    assert asset.symbol == "AAPL"
    assert asset.cik == "0000320193"
    cached, fresh = repository.get_cached_company(
        "AAPL", ttl_hours=168, now=datetime.now(UTC)
    )
    assert cached is not None and cached.cik == "0000320193"
    assert fresh is True

    with pytest.raises(ValueError, match="Conflicting CIK"):
        repository.set_known_company(
            symbol="AAPL",
            cik="0000000001",
            legal_name="Wrong Company",
            exchange="NYSE",
        )


@pytest.mark.parametrize("cik", ["320193", "000032019X", "00000320193"])
def test_bootstrap_requires_exactly_ten_cik_digits(db_session: Session, cik: str) -> None:
    with pytest.raises(ValueError, match="exactly 10 digits"):
        FundamentalRepository(db_session).set_known_company(
            symbol="AAPL", cik=cik, legal_name="Apple Inc.", exchange="Nasdaq"
        )
