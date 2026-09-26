import json
import logging
import re
import unicodedata
from dataclasses import fields, replace
from decimal import Decimal
from pathlib import Path
from typing import Any, TypeVar, overload

from sqlalchemy import String, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models import Asset, CompanyFiling, CompanyProfile, FinancialFact
from app.modules.fundamental_analysis.contracts import normalize_cik, normalize_symbol
from app.modules.fundamental_analysis.parsing import (
    ParsedFact,
    ParsedFiling,
    ParsedProfile,
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


class SecImportIdentityConflictError(SecImportError):
    code = "sec_import_identity_conflict"


class SecImportInvalidSymbolError(SecImportError):
    code = "sec_import_invalid_symbol"


def _reject_json_constant(value: str) -> None:
    raise ValueError("Non-finite JSON numbers are not accepted")


def decode_sec_json(raw: bytes) -> Any:
    """Decode offline financial tokens without ever passing through float."""
    try:
        return json.loads(
            raw.decode("utf-8-sig"), parse_float=Decimal,
            parse_constant=_reject_json_constant,
        )
    except (ValueError, UnicodeError, RecursionError):
        raise SecImportInvalidJsonError("SEC import file is not valid UTF-8 JSON") from None


def safe_source_filename(filename: str | None, *, fallback: str) -> str:
    """An untrusted provenance label, never a filesystem path."""
    name = re.split(r"[/\\]", filename or "")[-1]
    name = "".join(char for char in name if not unicodedata.category(char).startswith("C"))
    name = name.replace(":", "_").strip()
    limit = CompanyProfile.__table__.c.source_filename.type.length
    return name[:limit] if name and name not in {".", ".."} else fallback


@overload
def _model_text(model: Any, field: str, value: str) -> str: ...


@overload
def _model_text(model: Any, field: str, value: str | None) -> str | None: ...


def _model_text(model: Any, field: str, value: str | None) -> str | None:
    return value[:model.__table__.c[field].type.length] if value is not None else None


Record = TypeVar("Record", ParsedProfile, ParsedFiling, ParsedFact)


def _model_safe_record(
    record: Record, model: Any, error_type: type[SecImportError],
    *, identity_fields: frozenset[str] = frozenset(),
) -> Record:
    changes = {}
    for field in fields(record):
        column = model.__table__.c.get(field.name)
        value = getattr(record, field.name)
        if column is not None and isinstance(column.type, String) and isinstance(value, str):
            if len(value) > column.type.length:
                if field.name in identity_fields:
                    raise error_type("SEC identity field exceeds its supported length")
                changes[field.name] = value[:column.type.length]
    return replace(record, **changes)


def _read_json_file(raw_path: str | Path, *, max_file_mb: int) -> tuple[Path, Any]:
    path_text = str(raw_path)
    if LOCAL_URL_PATTERN.match(path_text):
        raise SecImportFileNotFoundError("Only local JSON files are accepted")
    try:
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
        with path.open("rb") as stream:
            raw = stream.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise SecImportFileTooLargeError(
                f"SEC JSON file exceeds the configured {max_file_mb} MB limit"
            )
        payload = decode_sec_json(raw)
    except SecImportError:
        raise
    except (OSError, ValueError, RuntimeError):
        raise SecImportInvalidJsonError("SEC import file is not valid UTF-8 JSON") from None
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


def _validate_submissions(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise SecImportInvalidSubmissionsError("SEC submissions root must be an object")
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


def _validate_companyfacts(payload: Any) -> None:
    if not isinstance(payload, dict) or not isinstance(payload.get("facts"), dict):
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
            return value or None
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
        submissions_path, submissions = _read_json_file(
            submissions_file, max_file_mb=self.max_file_mb
        )
        companyfacts_path, companyfacts = _read_json_file(
            companyfacts_file, max_file_mb=self.max_file_mb
        )
        return self.import_payloads(
            symbol=symbol, submissions=submissions, companyfacts=companyfacts,
            submissions_filename=submissions_path.name,
            companyfacts_filename=companyfacts_path.name,
        )

    def import_bytes(
        self, *, symbol: str, submissions: bytes, companyfacts: bytes,
        submissions_filename: str | None, companyfacts_filename: str | None,
    ) -> FundamentalSyncResult:
        max_bytes = self.max_file_mb * 1024 * 1024
        if self.max_file_mb <= 0 or max(len(submissions), len(companyfacts)) > max_bytes:
            raise SecImportFileTooLargeError("SEC JSON file exceeds the configured limit")
        return self.import_payloads(
            symbol=symbol, submissions=decode_sec_json(submissions),
            companyfacts=decode_sec_json(companyfacts),
            submissions_filename=submissions_filename,
            companyfacts_filename=companyfacts_filename,
        )

    def import_payloads(
        self, *, symbol: str, submissions: Any, companyfacts: Any,
        submissions_filename: str | None, companyfacts_filename: str | None,
    ) -> FundamentalSyncResult:
        """Common CLI/upload pipeline; owns the single commit and rollback."""
        _validate_submissions(submissions)
        _validate_companyfacts(companyfacts)
        submissions_cik = _payload_cik(submissions, companyfacts=False)
        companyfacts_cik = _payload_cik(companyfacts, companyfacts=True)
        if submissions_cik != companyfacts_cik:
            raise SecImportCikMismatchError("CIK differs between SEC JSON files")

        try:
            normalized_symbol = normalize_symbol(symbol)
        except ValueError:
            raise SecImportInvalidSymbolError("Invalid requested ticker symbol") from None
        tickers = submissions.get("tickers")
        normalized_tickers = set()
        if isinstance(tickers, list):
            for ticker in tickers:
                if isinstance(ticker, str):
                    try:
                        normalized_tickers.add(normalize_symbol(ticker))
                    except ValueError:
                        continue
        if normalized_symbol not in normalized_tickers:
            raise SecImportInvalidSubmissionsError(
                "Requested symbol must belong to SEC submissions.tickers"
            )

        submissions_filename = safe_source_filename(submissions_filename, fallback="submissions.json")
        companyfacts_filename = safe_source_filename(companyfacts_filename, fallback="companyfacts.json")
        legal_name = submissions["name"].strip()
        exchange = _exchange_for_symbol(submissions, normalized_symbol)
        try:
            profile = parse_company_profile(
                submissions, fallback_name=legal_name, cik=submissions_cik
            )
            filings = parse_filings(submissions, cik=submissions_cik)
            profile = _model_safe_record(profile, CompanyProfile, SecImportInvalidSubmissionsError)
            filings = [
                _model_safe_record(filing, CompanyFiling, SecImportInvalidSubmissionsError)
                for filing in filings
            ]
        except Exception:
            raise SecImportInvalidSubmissionsError(
                "SEC submissions JSON could not be parsed"
            ) from None
        try:
            facts, facts_rejected = parse_company_facts(
                companyfacts,
                filings=filings,
                fiscal_year_end=profile.fiscal_year_end,
            )
            facts = [
                _model_safe_record(
                    fact, FinancialFact, SecImportInvalidCompanyFactsError,
                    identity_fields=frozenset({"taxonomy", "concept", "unit", "frame"}),
                ) for fact in facts
            ]
        except Exception:
            raise SecImportInvalidCompanyFactsError(
                "SEC companyfacts JSON could not be parsed"
            ) from None

        imported_at = utc_now()
        try:
            if self.session.new or self.session.dirty or self.session.deleted:
                raise SecImportTransactionFailedError("Import requires a clean database session")
            asset = self.repository.get_asset(normalized_symbol)
            if asset is not None and asset.cik is not None:
                try:
                    asset_cik = normalize_cik(asset.cik)
                except ValueError:
                    raise SecImportIdentityConflictError(
                        "Asset contains an invalid saved CIK"
                    ) from None
                if asset_cik != submissions_cik:
                    raise SecImportIdentityConflictError(
                        "SEC JSON CIK does not match the saved Asset.cik"
                    )
            # Normalize legacy non-padded CIKs too; CIK is not a unique DB key.
            for other in self.session.scalars(
                select(Asset).where(Asset.cik.is_not(None)).order_by(Asset.id)
            ):
                if asset is not None and other.id == asset.id:
                    continue
                try:
                    same_cik = normalize_cik(other.cik) == submissions_cik
                except ValueError:
                    continue
                if same_cik:
                    raise SecImportIdentityConflictError(
                        f"SEC CIK is already associated with asset {other.symbol}"
                    )
            conflicting_filing = self.session.scalar(select(CompanyFiling).where(
                CompanyFiling.provider == "sec_edgar",
                CompanyFiling.accession_number.in_([filing.accession_number for filing in filings]),
                CompanyFiling.asset_id != (asset.id if asset else -1),
            ))
            if conflicting_filing is not None:
                raise SecImportIdentityConflictError("SEC filing belongs to a different asset")
            asset = self.repository.get_or_create_asset(
                symbol=normalized_symbol,
                legal_name=_model_text(Asset, "name", legal_name),
                exchange=_model_text(Asset, "exchange", exchange),
            )
            asset.cik = submissions_cik
            asset.sec_entity_name = _model_text(Asset, "sec_entity_name", profile.legal_name)
            asset.sec_exchange = _model_text(Asset, "sec_exchange", exchange)
            asset.sec_last_synced_at = imported_at
            if asset.exchange is None:
                asset.exchange = _model_text(Asset, "exchange", exchange)

            profile_created, profile_updated = self.repository.upsert_profile(
                asset_id=asset.id,
                provider="sec_edgar",
                profile=profile,
                received_at=imported_at,
                ingestion_method="manual_json",
                source_filename=submissions_filename,
                imported_at=imported_at,
            )
            filings_inserted, filings_updated = self.repository.upsert_filings(
                asset_id=asset.id,
                provider="sec_edgar",
                filings=filings,
                received_at=imported_at,
                ingestion_method="manual_json",
                source_filename=submissions_filename,
                imported_at=imported_at,
            )
            facts_inserted, facts_skipped = self.repository.insert_facts(
                asset_id=asset.id,
                provider="sec_edgar",
                facts=facts,
                received_at=imported_at,
                ingestion_method="manual_json",
                source_filename=companyfacts_filename,
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
