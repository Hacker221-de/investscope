import asyncio
from datetime import date
from decimal import Decimal

import pytest

from app.modules.fundamental_analysis.contracts import normalize_cik
from app.modules.fundamental_analysis.parsing import parse_company_facts, parse_filings
from app.modules.fundamental_analysis.sec_provider import SecEdgarFundamentalDataProvider
from app.modules.fundamental_analysis.xbrl import classify_period, normalized_metric_for


class TickerGateway:
    calls = 0

    async def get_ticker_index(self):
        self.calls += 1
        return {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [[320193, "Apple Inc.", "AAPL", "Nasdaq"]],
        }


def test_ticker_resolves_to_zero_padded_cik_case_insensitively_and_is_cached() -> None:
    gateway = TickerGateway()
    provider = SecEdgarFundamentalDataProvider(gateway)  # type: ignore[arg-type]

    async def run():
        first = await provider.resolve_company("aapl")
        second = await provider.resolve_company("AAPL")
        return first, second

    first, second = asyncio.run(run())
    assert first.cik == "0000320193"
    assert first.exchange == "Nasdaq"
    assert second == first
    assert gateway.calls == 1
    assert normalize_cik("42") == "0000000042"


def test_period_classification_does_not_infer_from_form() -> None:
    assert classify_period(None, date(2025, 3, 31)) == "instant"
    assert classify_period(date(2025, 1, 1), date(2025, 3, 31)) == "quarterly"
    assert classify_period(date(2025, 1, 1), date(2025, 9, 30)) == "ytd"
    assert classify_period(date(2025, 1, 1), date(2025, 12, 31)) == "annual"


def test_filings_keep_original_and_amendment_as_distinct_revisions() -> None:
    payload = {"filings": {"recent": {
        "accessionNumber": ["0000320193-25-000001", "0000320193-25-000002"],
        "filingDate": ["2025-02-01", "2025-02-10"],
        "reportDate": ["2024-12-31", "2024-12-31"],
        "acceptanceDateTime": ["2025-02-01T16:00:00Z", "2025-02-10T17:00:00Z"],
        "form": ["10-K", "10-K/A"],
        "primaryDocument": ["a10-k.htm", "a10-ka.htm"],
    }}}
    filings = parse_filings(payload, cik="0000320193")
    assert [filing.form for filing in filings] == ["10-K", "10-K/A"]
    assert filings[0].is_amendment is False
    assert filings[1].is_amendment is True
    assert filings[1].amended_form == "10-K"
    assert filings[0].accession_number != filings[1].accession_number


def test_companyfacts_preserves_decimal_negative_missing_and_period_types() -> None:
    entries = [
        {"start": "2025-01-01", "end": "2025-03-31", "val": 100,
         "accn": "0000320193-25-000001", "fy": 2025, "fp": "Q1",
         "form": "10-Q", "filed": "2025-05-01"},
        {"start": "2025-01-01", "end": "2025-09-30", "val": -20.5,
         "accn": "0000320193-25-000002", "fy": 2025, "fp": "Q3",
         "form": "10-Q", "filed": "2025-11-01"},
        {"start": "2025-01-01", "end": "2025-12-31", "val": "400.25",
         "accn": "0000320193-26-000003", "fy": 2025, "fp": "FY",
         "form": "10-K", "filed": "2026-02-01"},
        {"end": "2025-12-31", "val": None,
         "accn": "0000320193-26-000003", "form": "10-K", "filed": "2026-02-01"},
    ]
    payload = {"facts": {"us-gaap": {"Revenues": {
        "label": "Revenue", "description": "Revenue description",
        "units": {"USD": entries},
    }}}}
    facts, rejected = parse_company_facts(payload)
    assert [fact.period_type for fact in facts] == ["quarterly", "ytd", "annual"]
    assert facts[1].value == Decimal("-20.5")
    assert all(fact.normalized_metric == "revenue" for fact in facts)
    assert rejected == 1
    assert normalized_metric_for("Assets") == "total_assets"


def test_companyfacts_separates_instant_duration_and_quarterly_forms() -> None:
    payload = {"facts": {"us-gaap": {
        "Assets": {"units": {"USD": [{
            "end": "2025-03-31", "val": "10", "accn": "0000320193-25-000001",
            "form": "10-Q", "filed": "2025-05-01",
        }]}},
        "NetIncomeLoss": {"units": {"USD": [
            {"start": "2025-01-01", "end": "2025-03-31", "val": "1",
             "accn": "0000320193-25-000001", "form": "10-Q", "filed": "2025-05-01"},
            {"start": "2025-01-01", "end": "2025-09-30", "val": "3",
             "accn": "0000320193-25-000002", "form": "10-Q", "filed": "2025-11-01"},
        ]}},
    }}}
    facts, rejected = parse_company_facts(payload)
    assert rejected == 0
    assert [fact.period_type for fact in facts] == ["instant", "quarterly", "ytd"]
    assert [fact.is_instant for fact in facts] == [True, False, False]


def test_comparative_annual_fact_uses_economic_fiscal_year() -> None:
    submissions = {"filings": {"recent": {
        "accessionNumber": ["0000320193-19-000001", "0000320193-19-000002"],
        "filingDate": ["2019-10-31", "2019-11-15"],
        "reportDate": ["2019-09-28", "2018-09-29"],
        "acceptanceDateTime": ["20191031160000", "20191115160000"],
        "form": ["10-K", "10-K/A"],
        "primaryDocument": ["aapl-20190928.htm", "aapl-20180929a.htm"],
    }}}
    filings = parse_filings(submissions, cik="0000320193")
    payload = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        {
            "start": "2017-10-01", "end": "2018-09-29", "val": "265595",
            "accn": "0000320193-19-000001", "fy": 2019, "fp": "FY",
            "form": "10-K", "filed": "2019-10-31",
        },
        {
            "start": "2017-10-01", "end": "2018-09-29", "val": "265595",
            "accn": "0000320193-19-000002", "fy": 2019, "fp": "FY",
            "form": "10-K/A", "filed": "2019-11-15",
        },
    ]}}}}}

    facts, rejected = parse_company_facts(
        payload, filings=filings, fiscal_year_end="0929"
    )

    assert rejected == 0
    assert [fact.fiscal_year for fact in facts] == [2018, 2018]
    assert all(fact.period_start == date(2017, 10, 1) for fact in facts)


def test_quarterly_comparative_fy_is_validated_against_sec_fiscal_calendar() -> None:
    payload = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [{
        "start": "2017-10-01", "end": "2017-12-30", "val": "88293",
        "accn": "0000320193-19-000001", "fy": 2019, "fp": "Q1",
        "form": "10-Q", "filed": "2019-02-01",
    }]}}}}}

    facts, rejected = parse_company_facts(payload, fiscal_year_end="0929")

    assert rejected == 0
    assert facts[0].fiscal_year == 2018
