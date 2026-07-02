import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from app.modules.fundamental_analysis.contracts import SecInvalidResponseError
from app.modules.fundamental_analysis.xbrl import classify_period, normalized_metric_for

SUPPORTED_FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A"})
ACCESSION_PATTERN = re.compile(r"^\d{10}-\d{2}-\d{6}$")


class FiscalFilingContext(Protocol):
    form: str
    report_date: date | None


@dataclass(frozen=True, slots=True)
class ParsedProfile:
    cik: str
    legal_name: str
    sic: str | None
    sic_description: str | None
    entity_type: str | None
    state_of_incorporation: str | None
    fiscal_year_end: str | None
    exchanges: list[str]
    tickers: list[str]


@dataclass(frozen=True, slots=True)
class ParsedFiling:
    accession_number: str
    form: str
    filing_date: date
    report_date: date | None
    acceptance_datetime: datetime | None
    primary_document: str | None
    primary_doc_description: str | None
    file_number: str | None
    film_number: str | None
    items: str | None
    is_inline_xbrl: bool
    is_xbrl: bool
    is_amendment: bool
    amended_form: str | None
    filing_url: str | None


@dataclass(frozen=True, slots=True)
class ParsedFact:
    taxonomy: str
    concept: str
    label: str | None
    description: str | None
    normalized_metric: str | None
    unit: str
    value: Decimal
    period_start: date | None
    period_end: date
    filed_at: datetime
    frame: str | None
    fiscal_year: int | None
    fiscal_period: str | None
    form: str
    accession_number: str
    is_instant: bool
    period_type: str

    def persistence_key(self) -> tuple[Any, ...]:
        """Raw SEC identity, excluding metadata that normalization may correct."""
        return (
            self.taxonomy,
            self.concept,
            self.unit,
            self.value,
            self.period_start,
            self.period_end,
            self.filed_at,
            self.frame,
            self.form,
            self.accession_number,
        )

    def identity(self, *, asset_id: int, provider: str) -> str:
        payload = {
            "asset_id": asset_id,
            "provider": provider,
            "taxonomy": self.taxonomy,
            "concept": self.concept,
            "unit": self.unit,
            "value": str(self.value),
            "period_start": str(self.period_start) if self.period_start else None,
            "period_end": str(self.period_end),
            "filed_at": self.filed_at.isoformat(),
            "frame": self.frame,
            "form": self.form,
            "accession_number": self.accession_number,
        }
        serialized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date(value: Any, *, required: bool = False) -> date | None:
    text = _optional_text(value)
    if text is None:
        if required:
            raise ValueError("date is required")
        return None
    return date.fromisoformat(text)


def _acceptance_datetime(value: Any) -> datetime | None:
    text = _optional_text(value)
    if text is None:
        return None
    if re.fullmatch(r"\d{14}", text):
        return datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _boolean(value: Any) -> bool:
    return value is True or value in {1, "1", "true", "True", "TRUE"}


def _valid_fiscal_year(value: Any) -> int | None:
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if 1900 <= year <= 2200 else None


def _fiscal_year_end_month(value: str | None) -> int | None:
    text = _optional_text(value)
    if text is None or not re.fullmatch(r"\d{4}", text):
        return None
    month = int(text[:2])
    day = int(text[2:])
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    return month


def normalize_fiscal_year(
    raw_fiscal_year: Any,
    *,
    period_end: date,
    period_type: str,
    fiscal_period: str | None,
    form: str,
    filing: FiscalFilingContext | None = None,
    fiscal_year_end: str | None = None,
) -> int:
    """Resolve the economic fiscal year without deriving it from period_start."""
    raw_year = _valid_fiscal_year(raw_fiscal_year)
    normalized_period = (fiscal_period or "").upper()

    # An annual SEC fact belongs to the fiscal year in which that annual period
    # ends. A later filing may repeat it with the current filing's `fy`; that
    # comparative label is metadata for the filing, not the economic period.
    if period_type == "annual" or normalized_period == "FY":
        if raw_year == period_end.year:
            return raw_year
        if (
            filing is not None
            and filing.form in {"10-K", "10-K/A"}
            and filing.report_date is not None
            and abs((filing.report_date - period_end).days) <= 14
        ):
            return filing.report_date.year
        return period_end.year

    end_month = _fiscal_year_end_month(fiscal_year_end)
    expected_from_calendar = (
        period_end.year if end_month is None or period_end.month <= end_month
        else period_end.year + 1
    )
    if raw_year == expected_from_calendar:
        return raw_year
    if end_month is not None:
        return expected_from_calendar

    # Without issuer fiscal-calendar metadata, accept only a plausible SEC fy.
    if raw_year in {period_end.year, period_end.year + 1}:
        return raw_year
    return period_end.year


def parse_company_profile(payload: dict[str, Any], *, fallback_name: str, cik: str) -> ParsedProfile:
    exchanges = payload.get("exchanges")
    tickers = payload.get("tickers")
    if exchanges is not None and not isinstance(exchanges, list):
        raise SecInvalidResponseError("SEC profile exchanges have an invalid shape")
    if tickers is not None and not isinstance(tickers, list):
        raise SecInvalidResponseError("SEC profile tickers have an invalid shape")
    return ParsedProfile(
        cik=cik,
        legal_name=_optional_text(payload.get("name")) or fallback_name,
        sic=_optional_text(payload.get("sic")),
        sic_description=_optional_text(payload.get("sicDescription")),
        entity_type=_optional_text(payload.get("entityType")),
        state_of_incorporation=_optional_text(payload.get("stateOfIncorporation")),
        fiscal_year_end=_optional_text(payload.get("fiscalYearEnd")),
        exchanges=[str(value) for value in exchanges or [] if value],
        tickers=[str(value).upper() for value in tickers or [] if value],
    )


def _recent_value(recent: dict[str, Any], key: str, index: int) -> Any:
    values = recent.get(key)
    return values[index] if isinstance(values, list) and index < len(values) else None


def parse_filings(payload: dict[str, Any], *, cik: str) -> list[ParsedFiling]:
    filings = payload.get("filings")
    recent = filings.get("recent") if isinstance(filings, dict) else None
    if not isinstance(recent, dict):
        raise SecInvalidResponseError("SEC recent filings are missing")
    forms = recent.get("form")
    if not isinstance(forms, list):
        raise SecInvalidResponseError("SEC filing forms are missing")

    parsed: list[ParsedFiling] = []
    for index, raw_form in enumerate(forms):
        form = str(raw_form).strip().upper()
        if form not in SUPPORTED_FORMS:
            continue
        try:
            accession = str(_recent_value(recent, "accessionNumber", index)).strip()
            if not ACCESSION_PATTERN.fullmatch(accession):
                raise ValueError("invalid accession number")
            filing_date = _date(_recent_value(recent, "filingDate", index), required=True)
            assert filing_date is not None
            primary_document = _optional_text(_recent_value(recent, "primaryDocument", index))
            accession_path = accession.replace("-", "")
            filing_url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_path}/{primary_document}"
                if primary_document else None
            )
            is_amendment = form.endswith("/A")
            parsed.append(ParsedFiling(
                accession_number=accession,
                form=form,
                filing_date=filing_date,
                report_date=_date(_recent_value(recent, "reportDate", index)),
                acceptance_datetime=_acceptance_datetime(
                    _recent_value(recent, "acceptanceDateTime", index)
                ),
                primary_document=primary_document,
                primary_doc_description=_optional_text(
                    _recent_value(recent, "primaryDocDescription", index)
                ),
                file_number=_optional_text(_recent_value(recent, "fileNumber", index)),
                film_number=_optional_text(_recent_value(recent, "filmNumber", index)),
                items=_optional_text(_recent_value(recent, "items", index)),
                is_inline_xbrl=_boolean(_recent_value(recent, "isInlineXBRL", index)),
                is_xbrl=_boolean(_recent_value(recent, "isXBRL", index)),
                is_amendment=is_amendment,
                amended_form=form[:-2] if is_amendment else None,
                filing_url=filing_url,
            ))
        except (AssertionError, TypeError, ValueError):
            continue
    return parsed


def parse_company_facts(
    payload: dict[str, Any],
    *,
    filings: list[ParsedFiling] | None = None,
    fiscal_year_end: str | None = None,
) -> tuple[list[ParsedFact], int]:
    taxonomies = payload.get("facts")
    if not isinstance(taxonomies, dict):
        raise SecInvalidResponseError("SEC company facts are missing")

    parsed: list[ParsedFact] = []
    rejected = 0
    filings_by_accession = {
        filing.accession_number: filing for filing in filings or []
    }
    for taxonomy, concepts in taxonomies.items():
        if not isinstance(concepts, dict):
            rejected += 1
            continue
        for concept, definition in concepts.items():
            if not isinstance(definition, dict) or not isinstance(definition.get("units"), dict):
                rejected += 1
                continue
            taxonomy_text = str(taxonomy)
            concept_text = str(concept)
            if (
                not taxonomy_text
                or len(taxonomy_text) > 80
                or not concept_text
                or len(concept_text) > 180
            ):
                rejected += 1
                continue
            raw_label = _optional_text(definition.get("label"))
            raw_description = _optional_text(definition.get("description"))
            label = raw_label[:300] if raw_label else None
            description = raw_description[:2000] if raw_description else None
            for unit, entries in definition["units"].items():
                unit_text = str(unit)
                if not unit_text or len(unit_text) > 80:
                    rejected += 1
                    continue
                if not isinstance(entries, list):
                    rejected += 1
                    continue
                for entry in entries:
                    try:
                        if not isinstance(entry, dict) or entry.get("val") is None:
                            raise ValueError("fact value is missing")
                        raw_form = _optional_text(entry.get("form"))
                        if raw_form is None:
                            raise ValueError("fact form is missing")
                        form = raw_form.upper()
                        if form not in SUPPORTED_FORMS:
                            continue
                        accession = str(entry.get("accn", "")).strip()
                        if not ACCESSION_PATTERN.fullmatch(accession):
                            raise ValueError("invalid accession number")
                        value = Decimal(str(entry["val"]))
                        if not value.is_finite():
                            raise ValueError("fact value is not finite")
                        period_end = _date(entry.get("end"), required=True)
                        assert period_end is not None
                        period_start = _date(entry.get("start"))
                        period_type = classify_period(period_start, period_end)
                        filed_date = _date(entry.get("filed"), required=True)
                        assert filed_date is not None
                        fiscal_period = _optional_text(entry.get("fp"))
                        parsed.append(ParsedFact(
                            taxonomy=taxonomy_text,
                            concept=concept_text,
                            label=label,
                            description=description,
                            normalized_metric=normalized_metric_for(concept_text),
                            unit=unit_text,
                            value=value,
                            period_start=period_start,
                            period_end=period_end,
                            filed_at=datetime.combine(filed_date, time.min, tzinfo=UTC),
                            frame=_optional_text(entry.get("frame")),
                            fiscal_year=normalize_fiscal_year(
                                entry.get("fy"),
                                period_end=period_end,
                                period_type=period_type,
                                fiscal_period=fiscal_period,
                                form=form,
                                filing=filings_by_accession.get(accession),
                                fiscal_year_end=fiscal_year_end,
                            ),
                            fiscal_period=fiscal_period,
                            form=form,
                            accession_number=accession,
                            is_instant=period_start is None,
                            period_type=period_type,
                        ))
                    except (AssertionError, InvalidOperation, TypeError, ValueError):
                        rejected += 1
    return parsed, rejected
