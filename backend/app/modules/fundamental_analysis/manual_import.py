import json
import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.modules.fundamental_analysis.contracts import normalize_cik, normalize_symbol
from app.modules.fundamental_analysis.parsing import (
    parse_company_facts,
    parse_company_profile,
    parse_filings,
)
from app.modules.fundamental_analysis.sync import FundamentalSyncResult
from app.repositories.fundamentals import FundamentalRepository

logger = logging.getLogger(__name__)
LOCAL_URL_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


class SecImportError(RuntimeError):
    code = "sec_import_transaction_failed"


class SecImportFileNotFoundError(SecImportError):
    code = "sec_import_file_not_found"


class SecImportFileTooLargeError(SecImportError):
    code = "sec_import_file_too_large"


class SecImportInvalidJsonError(SecImportError):
    code = "sec_import_invalid_json"


class SecImportInvalidSubmissionsError(SecImportError):
    code = "sec_import_invalid_submissions"


class SecImportInvalidCompanyFactsError(SecImportError):
    code = "sec_import_invalid_companyfacts"


class SecImportCikMismatchError(SecImportError):
    code = "sec_import_cik_mismatch"


class SecImportTransactionFailedError(SecImportError):
    code = "sec_import_transaction_failed"


def _read_json_file(raw_path: str | Path, *, max_file_mb: int) -> tuple[Path, dict[str, Any]]:
    path_text = str(raw_path)
    if LOCAL_URL_PATTERN.match(path_text):
        raise SecImportFileNotFoundError("Only local JSON files are accepted")
    path = Path(path_text).expanduser()
    if not path.exists() or not path.is_file():
        raise SecImportFileNotFoundError("SEC JSON file was not found")
    if path.suffix.lower() != ".json":
        raise SecImportInvalidJsonError("SEC import file must use the .json extension")
    max_bytes = max_file_mb * 1024 * 1024
    if max_file_mb <= 0 or path.stat().st_size > max_bytes:
        raise SecImportFileTooLargeError(
            f"SEC JSON file exceeds the configured {max_file_mb} MB limit"
        )
    try:
        raw = path.read_bytes()
        if len(raw) > max_bytes:
            raise SecImportFileTooLargeError(
                f"SEC JSON file exceeds the configured {max_file_mb} MB limit"
            )
        payload = json.loads(raw.decode("utf-8-sig"))
    except SecImportError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise SecImportInvalidJsonError("SEC import file is not valid UTF-8 JSON") from None
    if not isinstance(payload, dict):
        raise SecImportInvalidJsonError("SEC import JSON root must be an object")
    return path, payload


def _payload_cik(payload: dict[str, Any], *, companyfacts: bool) -> str:
    error_type = (
        SecImportInvalidCompanyFactsError
        if companyfacts
        else SecImportInvalidSubmissionsError
    )
    if payload.get("cik") is None:
        raise error_type("SEC JSON does not contain CIK")
    try:
        return normalize_cik(payload["cik"])
    except ValueError:
        raise error_type("SEC JSON contains an invalid CIK") from None


def _validate_submissions(payload: dict[str, Any]) -> None:
    filings = payload.get("filings")
    if (
        not isinstance(payload.get("name"), str)
        or not payload["name"].strip()
        or not isinstance(filings, dict)
        or not isinstance(filings.get("recent"), dict)
    ):
        raise SecImportInvalidSubmissionsError(
            "JSON does not match the SEC submissions structure"
        )


def _validate_companyfacts(payload: dict[str, Any]) -> None:
    if not isinstance(payload.get("facts"), dict):
        raise SecImportInvalidCompanyFactsError(
            "JSON does not match the SEC companyfacts structure"
        )


def _exchange_for_symbol(payload: dict[str, Any], symbol: str) -> str | None:
    tickers = payload.get("tickers")
    exchanges = payload.get("exchanges")
    if not isinstance(tickers, list) or not isinstance(exchanges, list):
        return None
    for index, ticker in enumerate(tickers):
        if str(ticker).strip().upper() == symbol and index < len(exchanges):
            value = str(exchanges[index]).strip()
            return value[:80] or None
    return None


class SecManualJsonImportService:
    def __init__(self, session: Session, *, max_file_mb: int) -> None:
        self.session = session
        self.max_file_mb = max_file_mb
        self.repository = FundamentalRepository(session)

    def import_files(
        self,
        *,
        symbol: str,
        submissions_file: str | Path,
        companyfacts_file: str | Path,
    ) -> FundamentalSyncResult:
        normalized_symbol = normalize_symbol(symbol)
        submissions_path, submissions = _read_json_file(
            submissions_file, max_file_mb=self.max_file_mb
        )
        companyfacts_path, companyfacts = _read_json_file(
            companyfacts_file, max_file_mb=self.max_file_mb
        )
        _validate_submissions(submissions)
        _validate_companyfacts(companyfacts)
        submissions_cik = _payload_cik(submissions, companyfacts=False)
        companyfacts_cik = _payload_cik(companyfacts, companyfacts=True)
        if submissions_cik != companyfacts_cik:
            raise SecImportCikMismatchError("CIK differs between SEC JSON files")

        legal_name = submissions["name"].strip()[:240]
        exchange = _exchange_for_symbol(submissions, normalized_symbol)
        try:
            profile = parse_company_profile(
                submissions, fallback_name=legal_name, cik=submissions_cik
            )
            filings = parse_filings(submissions, cik=submissions_cik)
        except Exception as error:
            raise SecImportInvalidSubmissionsError(
                "SEC submissions JSON could not be parsed"
            ) from error
        try:
            facts, facts_rejected = parse_company_facts(
                companyfacts,
                filings=filings,
                fiscal_year_end=profile.fiscal_year_end,
            )
        except Exception as error:
            raise SecImportInvalidCompanyFactsError(
                "SEC companyfacts JSON could not be parsed"
            ) from error

        imported_at = utc_now()
        try:
            asset = self.repository.get_asset(normalized_symbol)
            if asset is not None and asset.cik is not None:
                try:
                    asset_cik = normalize_cik(asset.cik)
                except ValueError:
                    raise SecImportCikMismatchError(
                        "Asset contains an invalid saved CIK"
                    ) from None
                if asset_cik != submissions_cik:
                    raise SecImportCikMismatchError(
                        "SEC JSON CIK does not match the saved Asset.cik"
                    )
            asset = self.repository.get_or_create_asset(
                symbol=normalized_symbol,
                legal_name=legal_name,
                exchange=exchange,
            )
            asset.cik = submissions_cik
            asset.sec_entity_name = profile.legal_name
            asset.sec_exchange = exchange
            asset.sec_last_synced_at = imported_at
            if asset.exchange is None:
                asset.exchange = exchange

            profile_created, profile_updated = self.repository.upsert_profile(
                asset_id=asset.id,
                provider="sec_edgar",
                profile=profile,
                received_at=imported_at,
                ingestion_method="manual_json",
                source_filename=submissions_path.name,
                imported_at=imported_at,
            )
            filings_inserted, filings_updated = self.repository.upsert_filings(
                asset_id=asset.id,
                provider="sec_edgar",
                filings=filings,
                received_at=imported_at,
                ingestion_method="manual_json",
                source_filename=submissions_path.name,
                imported_at=imported_at,
            )
            facts_inserted, facts_skipped = self.repository.insert_facts(
                asset_id=asset.id,
                provider="sec_edgar",
                facts=facts,
                received_at=imported_at,
                ingestion_method="manual_json",
                source_filename=companyfacts_path.name,
                imported_at=imported_at,
            )
            self.session.commit()
        except SecImportError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise SecImportTransactionFailedError(
                "SEC JSON import transaction failed"
            ) from None

        logger.info(
            "Imported SEC JSON symbol=%s filings_inserted=%d facts_inserted=%d "
            "facts_skipped=%d facts_rejected=%d",
            normalized_symbol,
            filings_inserted,
            facts_inserted,
            facts_skipped,
            facts_rejected,
        )
        return FundamentalSyncResult(
            symbol=normalized_symbol,
            cik=submissions_cik,
            provider="sec_edgar",
            profile_created=profile_created,
            profile_updated=profile_updated,
            filings_inserted=filings_inserted,
            filings_updated=filings_updated,
            facts_inserted=facts_inserted,
            facts_skipped=facts_skipped,
            facts_rejected=facts_rejected,
            skipped=False,
            skip_reason=None,
            warning=None,
            received_at=imported_at,
        )
