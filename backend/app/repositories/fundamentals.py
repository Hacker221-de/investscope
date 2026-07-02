import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import ensure_utc, utc_now
from app.models import Asset, CompanyFiling, CompanyProfile, FinancialFact, SecTickerCache
from app.modules.fundamental_analysis.contracts import ResolvedCompany, normalize_symbol
from app.modules.fundamental_analysis.parsing import ParsedFact, ParsedFiling, ParsedProfile


class FundamentalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_asset(self, symbol: str) -> Asset | None:
        return self.session.scalar(select(Asset).where(Asset.symbol == symbol))

    def get_cached_company(
        self, symbol: str, *, ttl_hours: int, now: datetime
    ) -> tuple[ResolvedCompany | None, bool]:
        normalized = normalize_symbol(symbol)
        row = self.session.scalar(
            select(SecTickerCache).where(SecTickerCache.symbol == normalized)
        )
        if row is None:
            return None, False
        fetched_at = ensure_utc(row.fetched_at)
        is_fresh = ensure_utc(now) - fetched_at <= timedelta(hours=ttl_hours)
        return ResolvedCompany(
            symbol=row.symbol,
            cik=row.cik,
            legal_name=row.legal_name,
            exchange=row.exchange,
        ), is_fresh

    def store_cached_companies(
        self, companies: list[ResolvedCompany], *, fetched_at: datetime
    ) -> None:
        existing = {
            row.symbol: row for row in self.session.scalars(select(SecTickerCache))
        }
        try:
            for company in companies:
                row = existing.get(company.symbol)
                if row is None:
                    row = SecTickerCache(
                        symbol=company.symbol,
                        cik=company.cik,
                        legal_name=company.legal_name,
                        exchange=company.exchange,
                        fetched_at=fetched_at,
                    )
                    self.session.add(row)
                    existing[company.symbol] = row
                else:
                    row.cik = company.cik
                    row.legal_name = company.legal_name
                    row.exchange = company.exchange
                    row.fetched_at = fetched_at
                    row.updated_at = fetched_at
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def set_known_company(
        self, *, symbol: str, cik: str, legal_name: str, exchange: str | None
    ) -> Asset:
        normalized = normalize_symbol(symbol)
        if not re.fullmatch(r"\d{10}", cik):
            raise ValueError("CIK must contain exactly 10 digits")
        name = legal_name.strip()
        if not name or len(name) > 240:
            raise ValueError("Company name must contain between 1 and 240 characters")
        normalized_exchange = exchange.strip() if exchange else None
        if normalized_exchange and len(normalized_exchange) > 80:
            raise ValueError("Exchange must not exceed 80 characters")

        asset = self.get_asset(normalized)
        cached, _ = self.get_cached_company(normalized, ttl_hours=0, now=utc_now())
        for current_cik in (
            asset.cik if asset is not None else None,
            cached.cik if cached is not None else None,
        ):
            if current_cik is not None and current_cik != cik:
                raise ValueError(
                    f"Conflicting CIK for {normalized}: existing {current_cik}, requested {cik}"
                )

        asset = self.get_or_create_asset(
            symbol=normalized,
            legal_name=name,
            exchange=normalized_exchange,
        )
        asset.cik = cik
        asset.sec_entity_name = name
        asset.sec_exchange = normalized_exchange
        if asset.exchange is None:
            asset.exchange = normalized_exchange
        self.store_cached_companies(
            [
                ResolvedCompany(
                    symbol=normalized,
                    cik=cik,
                    legal_name=name,
                    exchange=normalized_exchange,
                )
            ],
            fetched_at=utc_now(),
        )
        return asset

    def get_or_create_asset(
        self, *, symbol: str, legal_name: str, exchange: str | None
    ) -> Asset:
        asset = self.get_asset(symbol)
        if asset is None:
            asset = Asset(
                symbol=symbol,
                name=legal_name,
                asset_type="Equity",
                exchange=exchange,
                currency="USD",
                sector=None,
                industry=None,
                provider_symbol=symbol,
                is_active=True,
            )
            self.session.add(asset)
            self.session.flush()
        return asset

    def get_profile(self, asset_id: int, provider: str = "sec_edgar") -> CompanyProfile | None:
        return self.session.scalar(select(CompanyProfile).where(
            CompanyProfile.asset_id == asset_id,
            CompanyProfile.provider == provider,
        ))

    def upsert_profile(
        self,
        *,
        asset_id: int,
        provider: str,
        profile: ParsedProfile,
        received_at: datetime,
        ingestion_method: str = "api",
        source_filename: str | None = None,
        imported_at: datetime | None = None,
    ) -> tuple[int, int]:
        current = self.get_profile(asset_id, provider)
        values: dict[str, Any] = {
            "cik": profile.cik,
            "legal_name": profile.legal_name,
            "sic": profile.sic,
            "sic_description": profile.sic_description,
            "entity_type": profile.entity_type,
            "state_of_incorporation": profile.state_of_incorporation,
            "fiscal_year_end": profile.fiscal_year_end,
            "exchanges": profile.exchanges,
            "tickers": profile.tickers,
            "ingestion_method": ingestion_method,
            "source_filename": source_filename,
            "imported_at": imported_at,
            "received_at": received_at,
        }
        if current is None:
            self.session.add(CompanyProfile(asset_id=asset_id, provider=provider, **values))
            return 1, 0
        for key, value in values.items():
            setattr(current, key, value)
        current.updated_at = utc_now()
        return 0, 1

    def upsert_filings(
        self,
        *,
        asset_id: int,
        provider: str,
        filings: list[ParsedFiling],
        received_at: datetime,
        ingestion_method: str = "api",
        source_filename: str | None = None,
        imported_at: datetime | None = None,
    ) -> tuple[int, int]:
        existing = {
            filing.accession_number: filing
            for filing in self.session.scalars(select(CompanyFiling).where(
                CompanyFiling.asset_id == asset_id,
                CompanyFiling.provider == provider,
            ))
        }
        inserted = 0
        updated = 0
        for parsed in filings:
            values = {
                "form": parsed.form,
                "filing_date": parsed.filing_date,
                "report_date": parsed.report_date,
                "acceptance_datetime": parsed.acceptance_datetime,
                "primary_document": parsed.primary_document,
                "primary_doc_description": parsed.primary_doc_description,
                "file_number": parsed.file_number,
                "film_number": parsed.film_number,
                "items": parsed.items,
                "is_inline_xbrl": parsed.is_inline_xbrl,
                "is_xbrl": parsed.is_xbrl,
                "is_amendment": parsed.is_amendment,
                "amended_form": parsed.amended_form,
                "filing_url": parsed.filing_url,
                "ingestion_method": ingestion_method,
                "source_filename": source_filename,
                "imported_at": imported_at,
                "received_at": received_at,
            }
            current = existing.get(parsed.accession_number)
            if current is None:
                current = CompanyFiling(
                    asset_id=asset_id,
                    provider=provider,
                    accession_number=parsed.accession_number,
                    **values,
                )
                self.session.add(current)
                existing[parsed.accession_number] = current
                inserted += 1
            else:
                for key, value in values.items():
                    setattr(current, key, value)
                updated += 1
        return inserted, updated

    def insert_facts(
        self,
        *,
        asset_id: int,
        provider: str,
        facts: list[ParsedFact],
        received_at: datetime,
        ingestion_method: str = "api",
        source_filename: str | None = None,
        imported_at: datetime | None = None,
    ) -> tuple[int, int]:
        existing = {
            row.fact_identity: row
            for row in self.session.scalars(select(FinancialFact).where(
                FinancialFact.asset_id == asset_id,
                FinancialFact.provider == provider,
            ))
        }
        existing_by_raw_key = {
            (
                row.taxonomy,
                row.concept,
                row.unit,
                row.value,
                row.period_start,
                row.period_end,
                row.filed_at,
                row.frame,
                row.form,
                row.accession_number,
            ): row
            for row in existing.values()
        }
        inserted = 0
        skipped = 0
        for fact in facts:
            identity = fact.identity(asset_id=asset_id, provider=provider)
            current = existing.get(identity) or existing_by_raw_key.get(
                fact.persistence_key()
            )
            if current is not None:
                current.fact_identity = identity
                current.label = fact.label
                current.description = fact.description
                current.normalized_metric = fact.normalized_metric
                current.fiscal_year = fact.fiscal_year
                current.fiscal_period = fact.fiscal_period
                current.is_instant = fact.is_instant
                current.period_type = fact.period_type
                if ingestion_method == "manual_json":
                    current.ingestion_method = ingestion_method
                    current.source_filename = source_filename
                    current.imported_at = imported_at
                existing[identity] = current
                skipped += 1
                continue
            new_fact = FinancialFact(
                asset_id=asset_id,
                provider=provider,
                taxonomy=fact.taxonomy,
                concept=fact.concept,
                label=fact.label,
                description=fact.description,
                normalized_metric=fact.normalized_metric,
                unit=fact.unit,
                value=fact.value,
                period_start=fact.period_start,
                period_end=fact.period_end,
                filed_at=fact.filed_at,
                frame=fact.frame,
                fiscal_year=fact.fiscal_year,
                fiscal_period=fact.fiscal_period,
                form=fact.form,
                accession_number=fact.accession_number,
                is_instant=fact.is_instant,
                period_type=fact.period_type,
                ingestion_method=ingestion_method,
                source_filename=source_filename,
                imported_at=imported_at,
                received_at=received_at,
                fact_identity=identity,
            )
            self.session.add(new_fact)
            existing[identity] = new_fact
            existing_by_raw_key[fact.persistence_key()] = new_fact
            inserted += 1
        return inserted, skipped

    @staticmethod
    def _filing_available(filing: CompanyFiling, as_of: datetime) -> bool:
        publication = filing.acceptance_datetime or datetime.combine(
            filing.filing_date, time.min, tzinfo=UTC
        )
        return ensure_utc(publication) <= as_of

    def list_filings(
        self,
        *,
        asset_id: int,
        provider: str = "sec_edgar",
        form: str | None = None,
        filed_from: date | None = None,
        filed_to: date | None = None,
        as_of: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CompanyFiling]:
        statement = select(CompanyFiling).where(
            CompanyFiling.asset_id == asset_id,
            CompanyFiling.provider == provider,
        )
        if form:
            statement = statement.where(CompanyFiling.form == form.upper())
        if filed_from:
            statement = statement.where(CompanyFiling.filing_date >= filed_from)
        if filed_to:
            statement = statement.where(CompanyFiling.filing_date <= filed_to)
        normalized_as_of = ensure_utc(as_of) if as_of is not None else None
        if normalized_as_of is not None:
            statement = statement.where(CompanyFiling.filing_date <= normalized_as_of.date())
        rows = list(self.session.scalars(statement.order_by(
            CompanyFiling.filing_date.desc(), CompanyFiling.accession_number.desc()
        )))
        if normalized_as_of is not None:
            rows = [row for row in rows if self._filing_available(row, normalized_as_of)]
        return rows[offset:offset + limit]

    def list_facts(
        self,
        *,
        asset_id: int,
        provider: str = "sec_edgar",
        metric: str | None = None,
        taxonomy: str | None = None,
        form: str | None = None,
        fiscal_year: int | None = None,
        fiscal_period: str | None = None,
        as_of: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FinancialFact]:
        statement = select(FinancialFact).where(
            FinancialFact.asset_id == asset_id,
            FinancialFact.provider == provider,
        )
        if metric:
            statement = statement.where(FinancialFact.normalized_metric == metric)
        if taxonomy:
            statement = statement.where(FinancialFact.taxonomy == taxonomy)
        if form:
            statement = statement.where(FinancialFact.form == form.upper())
        if fiscal_year is not None:
            statement = statement.where(FinancialFact.fiscal_year == fiscal_year)
        if fiscal_period:
            statement = statement.where(FinancialFact.fiscal_period == fiscal_period.upper())
        normalized_as_of = ensure_utc(as_of) if as_of is not None else None
        if normalized_as_of is not None:
            statement = statement.where(FinancialFact.filed_at <= normalized_as_of)
        rows = list(self.session.scalars(statement.order_by(
            FinancialFact.period_end.desc(),
            FinancialFact.filed_at.desc(),
            FinancialFact.id.desc(),
        )))
        if normalized_as_of is not None:
            accessions = {row.accession_number for row in rows}
            filings = {
                row.accession_number: row
                for row in self.session.scalars(select(CompanyFiling).where(
                    CompanyFiling.provider == provider,
                    CompanyFiling.accession_number.in_(accessions),
                ))
            } if accessions else {}
            rows = [
                row for row in rows
                if row.accession_number not in filings
                or self._filing_available(filings[row.accession_number], normalized_as_of)
            ]
        return rows[offset:offset + limit]
