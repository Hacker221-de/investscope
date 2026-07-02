import copy
from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Asset, CompanyFiling, CompanyProfile, FinancialFact
from app.commands import fundamentals as fundamentals_command
from app.modules.fundamental_analysis.manual_import import (
    SecImportCikMismatchError,
    SecImportFileNotFoundError,
    SecImportFileTooLargeError,
    SecImportInvalidCompanyFactsError,
    SecImportInvalidJsonError,
    SecImportInvalidSubmissionsError,
    SecImportTransactionFailedError,
    SecManualJsonImportService,
)
from app.repositories import FundamentalRepository


def submissions_payload() -> dict:
    return {
        "cik": "0000320193",
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
    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {"us-gaap": {"NetIncomeLoss": {
            "label": "Net income",
            "description": "Net income or loss",
            "units": {"USD": [
                {
                    "start": "2024-01-01", "end": "2024-12-31", "val": "100.25",
                    "accn": "0000320193-25-000001", "fy": 2024, "fp": "FY",
                    "form": "10-K", "filed": "2025-02-01", "frame": "CY2024",
                },
                {
                    "start": "2024-01-01", "end": "2024-12-31", "val": "-9.75",
                    "accn": "0000320193-25-000002", "fy": 2024, "fp": "FY",
                    "form": "10-K/A", "filed": "2025-02-10", "frame": "CY2024",
                },
                {
                    "start": "2024-01-01", "end": "2024-12-31", "val": None,
                    "accn": "0000320193-25-000002", "fy": 2024, "fp": "FY",
                    "form": "10-K/A", "filed": "2025-02-10",
                },
            ]},
        }}},
    }


def write_payloads(
    tmp_path: Path,
    *,
    submissions: dict | None = None,
    companyfacts: dict | None = None,
) -> tuple[Path, Path]:
    submissions_path = tmp_path / "submissions.json"
    companyfacts_path = tmp_path / "companyfacts.json"
    submissions_path.write_text(
        json.dumps(submissions if submissions is not None else submissions_payload()),
        encoding="utf-8",
    )
    companyfacts_path.write_text(
        json.dumps(companyfacts if companyfacts is not None else companyfacts_payload()),
        encoding="utf-8",
    )
    return submissions_path, companyfacts_path


def import_payloads(
    db_session: Session,
    submissions_path: Path,
    companyfacts_path: Path,
    *,
    max_file_mb: int = 100,
):
    return SecManualJsonImportService(
        db_session, max_file_mb=max_file_mb
    ).import_files(
        symbol="AAPL",
        submissions_file=submissions_path,
        companyfacts_file=companyfacts_path,
    )


def test_valid_manual_import_preserves_amendment_missing_and_negative_values(
    db_session: Session,
    tmp_path: Path,
) -> None:
    paths = write_payloads(tmp_path)
    result = import_payloads(db_session, *paths)

    assert result.provider == "sec_edgar"
    assert result.cik == "0000320193"
    assert result.profile_created == 1
    assert result.filings_inserted == 2
    assert result.facts_inserted == 2
    assert result.facts_rejected == 1
    asset = db_session.scalar(select(Asset).where(Asset.symbol == "AAPL"))
    assert asset is not None and asset.cik == "0000320193"
    filings = list(db_session.scalars(select(CompanyFiling).order_by(CompanyFiling.form)))
    assert [row.form for row in filings] == ["10-K", "10-K/A"]
    assert filings[1].is_amendment is True
    facts = list(db_session.scalars(select(FinancialFact).order_by(FinancialFact.value)))
    assert [str(row.value) for row in facts] == ["-9.7500000000", "100.2500000000"]
    assert all(row.ingestion_method == "manual_json" for row in facts)
    assert all(row.source_filename == "companyfacts.json" for row in facts)
    profile = db_session.scalar(select(CompanyProfile))
    assert profile is not None
    assert profile.ingestion_method == "manual_json"
    assert profile.source_filename == "submissions.json"
    assert profile.imported_at is not None


def test_duplicate_manual_import_is_idempotent(db_session: Session, tmp_path: Path) -> None:
    paths = write_payloads(tmp_path)
    first = import_payloads(db_session, *paths)
    second = import_payloads(db_session, *paths)

    assert first.facts_inserted == 2
    assert second.profile_updated == 1
    assert second.filings_inserted == 0
    assert second.filings_updated == 2
    assert second.facts_inserted == 0
    assert second.facts_skipped == 2
    assert second.facts_rejected == 1
    assert db_session.scalar(select(func.count()).select_from(CompanyFiling)) == 2
    assert db_session.scalar(select(func.count()).select_from(FinancialFact)) == 2


def test_manual_import_corrects_comparative_annual_fiscal_year_and_api_series(
    market_client: TestClient,
    db_session: Session,
    tmp_path: Path,
) -> None:
    submissions = submissions_payload()
    submissions["fiscalYearEnd"] = "0929"
    submissions["filings"]["recent"] = {
        "accessionNumber": ["0000320193-19-000001"],
        "filingDate": ["2019-10-31"],
        "reportDate": ["2019-09-28"],
        "acceptanceDateTime": ["20191031160000"],
        "form": ["10-K"],
        "primaryDocument": ["aapl-20190928.htm"],
        "primaryDocDescription": ["Annual report"],
        "fileNumber": ["001-00001"],
        "filmNumber": ["191"],
        "items": [""],
        "isXBRL": [1],
        "isInlineXBRL": [1],
    }
    companyfacts = {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {"us-gaap": {"Revenues": {
            "units": {"USD": [{
                "start": "2017-10-01", "end": "2018-09-29", "val": "265595",
                "accn": "0000320193-19-000001", "fy": 2019, "fp": "FY",
                "form": "10-K", "filed": "2019-10-31", "frame": "CY2018",
            }]},
        }}},
    }
    paths = write_payloads(
        tmp_path, submissions=submissions, companyfacts=companyfacts
    )

    first = import_payloads(db_session, *paths)
    fact = db_session.scalar(select(FinancialFact))
    assert fact is not None
    assert fact.fiscal_year == 2018
    assert fact.ingestion_method == "manual_json"
    assert fact.source_filename == "companyfacts.json"

    # Simulate a row written by the previous normalizer. Re-import updates its
    # normalized metadata using the raw SEC identity instead of duplicating it.
    fact.fiscal_year = 2019
    fact.fact_identity = "legacy-fiscal-year-identity"
    db_session.commit()
    second = import_payloads(db_session, *paths)
    assert second.facts_inserted == 0
    assert second.facts_skipped == 1
    assert db_session.scalar(select(func.count()).select_from(FinancialFact)) == 1
    db_session.refresh(fact)
    assert fact.fiscal_year == 2018

    response = market_client.get(
        "/api/fundamentals/AAPL/metrics",
        params={"period_type": "annual", "limit": 5},
    )
    assert response.status_code == 200
    annual = response.json()["metrics"]["revenue"][0]
    assert annual["period_start"] == "2017-10-01"
    assert annual["period_end"] == "2018-09-29"
    assert annual["fiscal_year"] == 2018
    facts_response = market_client.get(
        "/api/fundamentals/AAPL/facts", params={"metric": "revenue"}
    )
    assert facts_response.status_code == 200
    assert facts_response.json()[0]["fiscal_year"] == 2018


def test_manual_import_rejects_malformed_json(db_session: Session, tmp_path: Path) -> None:
    submissions_path, companyfacts_path = write_payloads(tmp_path)
    submissions_path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(SecImportInvalidJsonError) as captured:
        import_payloads(db_session, submissions_path, companyfacts_path)
    assert captured.value.code == "sec_import_invalid_json"


def test_manual_import_rejects_missing_file(db_session: Session, tmp_path: Path) -> None:
    _, companyfacts_path = write_payloads(tmp_path)
    with pytest.raises(SecImportFileNotFoundError) as captured:
        import_payloads(db_session, tmp_path / "missing.json", companyfacts_path)
    assert captured.value.code == "sec_import_file_not_found"


def test_manual_import_rejects_url_without_network_access(
    db_session: Session,
    tmp_path: Path,
) -> None:
    _, companyfacts_path = write_payloads(tmp_path)
    with pytest.raises(SecImportFileNotFoundError):
        SecManualJsonImportService(db_session, max_file_mb=100).import_files(
            symbol="AAPL",
            submissions_file="https://data.sec.gov/submissions/CIK0000320193.json",
            companyfacts_file=companyfacts_path,
        )


def test_manual_import_rejects_oversized_file(db_session: Session, tmp_path: Path) -> None:
    paths = write_payloads(tmp_path)
    with pytest.raises(SecImportFileTooLargeError) as captured:
        import_payloads(db_session, *paths, max_file_mb=0)
    assert captured.value.code == "sec_import_file_too_large"


def test_manual_import_rejects_cik_mismatch(db_session: Session, tmp_path: Path) -> None:
    companyfacts = copy.deepcopy(companyfacts_payload())
    companyfacts["cik"] = 789019
    paths = write_payloads(tmp_path, companyfacts=companyfacts)
    with pytest.raises(SecImportCikMismatchError) as captured:
        import_payloads(db_session, *paths)
    assert captured.value.code == "sec_import_cik_mismatch"
    assert db_session.scalar(select(func.count()).select_from(Asset)) == 0


def test_manual_import_requires_file_cik_to_match_saved_asset(
    db_session: Session,
    tmp_path: Path,
) -> None:
    repository = FundamentalRepository(db_session)
    repository.set_known_company(
        symbol="AAPL",
        cik="0000000001",
        legal_name="Conflicting company",
        exchange="Nasdaq",
    )
    paths = write_payloads(tmp_path)
    with pytest.raises(SecImportCikMismatchError):
        import_payloads(db_session, *paths)
    asset = repository.get_asset("AAPL")
    assert asset is not None and asset.cik == "0000000001"


def test_manual_import_validates_expected_sec_structures(
    db_session: Session,
    tmp_path: Path,
) -> None:
    paths = write_payloads(tmp_path, submissions={"cik": 320193})
    with pytest.raises(SecImportInvalidSubmissionsError) as submissions_error:
        import_payloads(db_session, *paths)
    assert submissions_error.value.code == "sec_import_invalid_submissions"

    paths = write_payloads(tmp_path, companyfacts={"cik": 320193, "unexpected": {}})
    with pytest.raises(SecImportInvalidCompanyFactsError) as facts_error:
        import_payloads(db_session, *paths)
    assert facts_error.value.code == "sec_import_invalid_companyfacts"


def test_manual_import_rolls_back_whole_transaction(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_payloads(tmp_path)

    def fail_insert(*args, **kwargs):
        raise RuntimeError("database failure")

    monkeypatch.setattr(FundamentalRepository, "insert_facts", fail_insert)
    with pytest.raises(SecImportTransactionFailedError) as captured:
        import_payloads(db_session, *paths)
    assert captured.value.code == "sec_import_transaction_failed"
    assert db_session.scalar(select(func.count()).select_from(Asset)) == 0
    assert db_session.scalar(select(func.count()).select_from(CompanyProfile)) == 0
    assert db_session.scalar(select(func.count()).select_from(CompanyFiling)) == 0


def test_manual_import_never_uses_http(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = write_payloads(tmp_path)

    def network_forbidden(*args, **kwargs):
        raise AssertionError("network access is forbidden during manual import")

    monkeypatch.setattr(httpx.Client, "request", network_forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "request", network_forbidden)
    result = import_payloads(db_session, *paths)
    assert result.facts_inserted == 2


def test_existing_get_endpoints_read_manually_imported_data(
    market_client: TestClient,
    db_session: Session,
    tmp_path: Path,
) -> None:
    paths = write_payloads(tmp_path)
    import_payloads(db_session, *paths)

    profile = market_client.get("/api/fundamentals/AAPL/profile")
    filings = market_client.get("/api/fundamentals/AAPL/filings")
    facts = market_client.get(
        "/api/fundamentals/AAPL/facts", params={"metric": "net_income"}
    )
    assert profile.status_code == 200
    assert profile.json()["ingestion_method"] == "manual_json"
    assert profile.json()["provider"] == "sec_edgar"
    assert filings.status_code == 200
    assert {row["form"] for row in filings.json()} == {"10-K", "10-K/A"}
    assert all(row["ingestion_method"] == "manual_json" for row in filings.json())
    assert facts.status_code == 200
    assert len(facts.json()) == 2
    assert all(row["source_filename"] == "companyfacts.json" for row in facts.json())


def test_import_sec_json_cli_returns_sync_statistics(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    submissions_path, companyfacts_path = write_payloads(tmp_path)

    @contextmanager
    def session_local():
        yield db_session

    monkeypatch.setattr(fundamentals_command, "SessionLocal", session_local)
    monkeypatch.setattr(
        fundamentals_command,
        "get_settings",
        lambda: SimpleNamespace(sec_import_max_file_mb=100),
    )
    exit_code = fundamentals_command.main([
        "import-sec-json",
        "--symbol", "AAPL",
        "--submissions-file", str(submissions_path),
        "--companyfacts-file", str(companyfacts_path),
    ])
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["provider"] == "sec_edgar"
    assert output["facts_inserted"] == 2
    assert output["facts_rejected"] == 1
