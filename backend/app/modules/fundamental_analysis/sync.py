import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.modules.fundamental_analysis.contracts import FundamentalDataProvider, ResolvedCompany
from app.modules.fundamental_analysis.parsing import (
    parse_company_facts,
    parse_company_profile,
    parse_filings,
)
from app.repositories.fundamentals import FundamentalRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FundamentalSyncResult:
    symbol: str
    cik: str
    provider: str
    profile_created: int
    profile_updated: int
    filings_inserted: int
    filings_updated: int
    facts_inserted: int
    facts_skipped: int
    facts_rejected: int
    skipped: bool
    skip_reason: str | None
    warning: str | None
    received_at: datetime


class FundamentalSyncService:
    def __init__(
        self,
        session: Session,
        provider: FundamentalDataProvider,
        *,
        cache_ttl_hours: int,
    ) -> None:
        self.session = session
        self.provider = provider
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.repository = FundamentalRepository(session)

    async def synchronize(self, symbol: str) -> FundamentalSyncResult:
        normalize_symbol = getattr(self.provider, "normalize_symbol", None)
        normalized = normalize_symbol(symbol) if normalize_symbol else symbol.strip().upper()
        received_at = utc_now()
        existing_asset = self.repository.get_asset(normalized)
        if (
            existing_asset is not None
            and existing_asset.cik is not None
            and existing_asset.sec_last_synced_at is not None
            and received_at - existing_asset.sec_last_synced_at < self.cache_ttl
        ):
            return FundamentalSyncResult(
                symbol=normalized,
                cik=existing_asset.cik,
                provider=self.provider.name,
                profile_created=0,
                profile_updated=0,
                filings_inserted=0,
                filings_updated=0,
                facts_inserted=0,
                facts_skipped=0,
                facts_rejected=0,
                skipped=True,
                skip_reason="fresh_data",
                warning=None,
                received_at=received_at,
            )

        try:
            if (
                existing_asset is not None
                and existing_asset.cik is not None
                and re.fullmatch(r"\d{10}", existing_asset.cik)
            ):
                company = ResolvedCompany(
                    symbol=normalized,
                    cik=existing_asset.cik,
                    legal_name=existing_asset.sec_entity_name or existing_asset.name,
                    exchange=existing_asset.sec_exchange or existing_asset.exchange,
                )
            else:
                company = await self.provider.resolve_company(normalized)
            submissions = await self.provider.get_submissions(company.cik)
            facts_payload = await self.provider.get_company_facts(company.cik)

            profile = parse_company_profile(
                submissions, fallback_name=company.legal_name, cik=company.cik
            )
            filings = parse_filings(submissions, cik=company.cik)
            facts, facts_rejected = parse_company_facts(
                facts_payload,
                filings=filings,
                fiscal_year_end=profile.fiscal_year_end,
            )
            if facts_rejected:
                logger.warning(
                    "Rejected malformed SEC facts provider=%s symbol=%s count=%d",
                    self.provider.name,
                    normalized,
                    facts_rejected,
                )

            asset = self.repository.get_or_create_asset(
                symbol=company.symbol,
                legal_name=company.legal_name,
                exchange=company.exchange,
            )
            asset.cik = company.cik
            asset.sec_entity_name = profile.legal_name
            asset.sec_exchange = company.exchange
            asset.sec_last_synced_at = received_at
            if asset.exchange is None and company.exchange is not None:
                asset.exchange = company.exchange

            profile_created, profile_updated = self.repository.upsert_profile(
                asset_id=asset.id,
                provider=self.provider.name,
                profile=profile,
                received_at=received_at,
            )
            filings_inserted, filings_updated = self.repository.upsert_filings(
                asset_id=asset.id,
                provider=self.provider.name,
                filings=filings,
                received_at=received_at,
            )
            facts_inserted, facts_skipped = self.repository.insert_facts(
                asset_id=asset.id,
                provider=self.provider.name,
                facts=facts,
                received_at=received_at,
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        return FundamentalSyncResult(
            symbol=company.symbol,
            cik=company.cik,
            provider=self.provider.name,
            profile_created=profile_created,
            profile_updated=profile_updated,
            filings_inserted=filings_inserted,
            filings_updated=filings_updated,
            facts_inserted=facts_inserted,
            facts_skipped=facts_skipped,
            facts_rejected=facts_rejected,
            skipped=False,
            skip_reason=None,
            warning=company.warning,
            received_at=received_at,
        )
