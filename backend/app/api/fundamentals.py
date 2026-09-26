import re
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData, UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException, MultiPartParser

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.local_request_security import require_local_request
from app.core.time import ensure_utc
from app.modules.fundamental_analysis import (
    FundamentalDataProvider,
    SecEdgarFundamentalDataProvider,
)
from app.modules.fundamental_analysis.contracts import SecProviderError
from app.modules.fundamental_analysis.parsing import (
    SUPPORTED_FORMS,
    normalize_fiscal_year,
)
from app.modules.fundamental_analysis.metrics import FundamentalMetricsService
from app.modules.fundamental_analysis.manual_import import (
    SecImportError,
    SecImportFileTooLargeError,
    SecImportIdentityConflictError,
    SecImportInvalidJsonError,
    SecImportTransactionFailedError,
    SecManualJsonImportService,
)
from app.modules.fundamental_analysis.sec_gateway import SecEdgarRequestGateway
from app.modules.fundamental_analysis.sync import FundamentalSyncService
from app.repositories import FundamentalRepository
from app.schemas.fundamentals import (
    CompanyFilingView,
    CompanyProfileView,
    FinancialFactView,
    FundamentalSyncView,
    FundamentalMetricsView,
)

router = APIRouter(prefix="/fundamentals", tags=["fundamentals"])
TICKER_PATTERN = re.compile(r"^[A-Z0-9.\-]{1,16}$")


def get_fundamental_provider(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db)],
) -> FundamentalDataProvider:
    gateway = SecEdgarRequestGateway(
        user_agent=settings.sec_user_agent,
        max_requests_per_second=settings.sec_max_requests_per_second,
        cache_ttl_hours=settings.sec_cache_ttl_hours,
        timeout_seconds=settings.sec_request_timeout_seconds,
        session=session,
    )
    return SecEdgarFundamentalDataProvider(
        gateway,
        ticker_cache=FundamentalRepository(session),
        ticker_cache_ttl_hours=settings.sec_ticker_cache_ttl_hours,
    )


def _symbol(value: str) -> str:
    normalized = value.strip().upper()
    if not TICKER_PATTERN.fullmatch(normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ticker must contain only ASCII letters, digits, dot or hyphen",
        )
    return normalized


def _form(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if normalized not in SUPPORTED_FORMS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Form must be one of: {', '.join(sorted(SUPPORTED_FORMS))}",
        )
    return normalized


def _as_of(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    try:
        return ensure_utc(value)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="as_of must include a timezone",
        ) from error


def _asset_or_404(repository: FundamentalRepository, symbol: str):
    asset = repository.get_asset(symbol)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.get("/{symbol}/profile", response_model=CompanyProfileView)
def company_profile(
    symbol: str,
    session: Annotated[Session, Depends(get_db)],
) -> CompanyProfileView:
    repository = FundamentalRepository(session)
    asset = _asset_or_404(repository, _symbol(symbol))
    profile = repository.get_profile(asset.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="SEC profile is not synchronized")
    return CompanyProfileView.model_validate(profile)


@router.get("/{symbol}/filings", response_model=list[CompanyFilingView])
def company_filings(
    symbol: str,
    session: Annotated[Session, Depends(get_db)],
    form: str | None = None,
    filed_from: date | None = None,
    filed_to: date | None = None,
    as_of: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CompanyFilingView]:
    if filed_from and filed_to and filed_from > filed_to:
        raise HTTPException(status_code=422, detail="filed_from must not be after filed_to")
    repository = FundamentalRepository(session)
    asset = _asset_or_404(repository, _symbol(symbol))
    rows = repository.list_filings(
        asset_id=asset.id,
        form=_form(form),
        filed_from=filed_from,
        filed_to=filed_to,
        as_of=_as_of(as_of),
        limit=limit,
        offset=offset,
    )
    return [CompanyFilingView.model_validate(row) for row in rows]


@router.get("/{symbol}/facts", response_model=list[FinancialFactView])
def company_facts(
    symbol: str,
    session: Annotated[Session, Depends(get_db)],
    metric: Annotated[str | None, Query(max_length=80)] = None,
    taxonomy: Annotated[str | None, Query(max_length=80)] = None,
    form: str | None = None,
    fiscal_year: Annotated[int | None, Query(ge=1900, le=2200)] = None,
    fiscal_period: Annotated[str | None, Query(max_length=16)] = None,
    as_of: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[FinancialFactView]:
    repository = FundamentalRepository(session)
    asset = _asset_or_404(repository, _symbol(symbol))
    rows = repository.list_facts(
        asset_id=asset.id,
        metric=metric,
        taxonomy=taxonomy,
        form=_form(form),
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        as_of=_as_of(as_of),
        limit=limit,
        offset=offset,
    )
    profile = repository.get_profile(asset.id)
    filings = {
        filing.accession_number: filing
        for filing in repository.list_filings(
            asset_id=asset.id,
            as_of=_as_of(as_of),
            limit=100_000,
        )
    }
    return [
        FinancialFactView.model_validate(row).model_copy(update={
            "fiscal_year": normalize_fiscal_year(
                row.fiscal_year,
                period_end=row.period_end,
                period_type=row.period_type,
                fiscal_period=row.fiscal_period,
                form=row.form,
                filing=filings.get(row.accession_number),
                fiscal_year_end=profile.fiscal_year_end if profile else None,
            )
        })
        for row in rows
    ]


@router.get("/{symbol}/metrics", response_model=FundamentalMetricsView)
def fundamental_metrics(
    symbol: str,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    period_type: Literal["quarterly", "annual", "ttm"] = "quarterly",
    as_of: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 12,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_alternatives: bool = False,
    annual_fallback: bool = False,
) -> FundamentalMetricsView:
    normalized = _symbol(symbol)
    service = FundamentalMetricsService(
        session,
        market_provider=settings.market_data_provider,
        market_stale_after_hours=settings.market_data_stale_after_hours,
        market_session_close_hour_utc=settings.market_daily_session_close_hour_utc,
    )
    try:
        result = service.build_metrics(
            symbol=normalized,
            period_type=period_type,
            as_of=_as_of(as_of),
            limit=limit,
            offset=offset,
            include_alternatives=include_alternatives,
            annual_fallback=annual_fallback,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return FundamentalMetricsView.model_validate(result)


@router.post("/{symbol}/sync", response_model=FundamentalSyncView)
async def sync_fundamentals(
    symbol: str,
    session: Annotated[Session, Depends(get_db)],
    provider: Annotated[FundamentalDataProvider, Depends(get_fundamental_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FundamentalSyncView:
    normalized = _symbol(symbol)
    service = FundamentalSyncService(
        session, provider, cache_ttl_hours=settings.sec_cache_ttl_hours
    )
    try:
        result = await service.synchronize(normalized)
    except SecProviderError as error:
        messages = {
            "sec_company_not_found": "Компания не найдена в SEC EDGAR",
            "sec_rate_limit": "SEC временно ограничила частоту запросов",
            "sec_access_denied": "SEC отклонила запрос приложения",
            "sec_timeout": "SEC не ответила за отведённое время",
            "sec_invalid_response": "SEC вернула некорректный ответ",
            "sec_unavailable": "Сервис SEC временно недоступен",
        }
        raise HTTPException(
            status_code=error.http_status,
            detail={
                "code": error.code,
                "provider": provider.name,
                "message": messages.get(error.code, messages["sec_unavailable"]),
            },
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return FundamentalSyncView.model_validate(result)


def _validate_import_headers(request: Request, max_file_bytes: int) -> None:
    content_types = request.headers.getlist("content-type")
    if len(content_types) != 1:
        raise HTTPException(status_code=415, detail="Expected multipart/form-data")
    media_type, _ = parse_options_header(content_types[0])
    if media_type.lower() != b"multipart/form-data":
        raise HTTPException(status_code=415, detail="Expected multipart/form-data")
    lengths = request.headers.getlist("content-length")
    if lengths:
        if len(lengths) != 1 or re.fullmatch(r"[0-9]+", lengths[0]) is None:
            raise HTTPException(status_code=400, detail="Invalid Content-Length")
        # Compare decimal strings first: an arbitrarily long integer is still
        # oversized, without invoking Python's integer conversion length limit.
        length = lengths[0].lstrip("0") or "0"
        ceiling = str(2 * max_file_bytes + 1024 * 1024)
        if len(length) > len(ceiling) or (len(length) == len(ceiling) and length > ceiling):
            raise HTTPException(status_code=413, detail="SEC upload exceeds the request size limit")


async def _read_import_upload(upload: UploadFile, max_file_bytes: int) -> bytes:
    if upload.size is not None and upload.size > max_file_bytes:
        raise SecImportFileTooLargeError("SEC JSON file exceeds the configured limit")
    chunks = bytearray()
    while True:
        chunk = await upload.read(min(64 * 1024, max_file_bytes - len(chunks) + 1))
        if not chunk:
            return bytes(chunks)
        chunks.extend(chunk)
        if len(chunks) > max_file_bytes:
            raise SecImportFileTooLargeError("SEC JSON file exceeds the configured limit")


class _ClosingMultipartParser(MultiPartParser):
    """Lifecycle adapter only: Starlette/python-multipart still parse the body.

    Starlette 1.3 does not close its spooled files on MultipartParseError or on
    truncated input, and python-multipart.finalize() does not validate EOF.
    Keep this fix endpoint-local; never patch the global parser/middleware.
    """

    _finished = False

    def on_end(self) -> None:
        super().on_end()
        self._finished = True

    async def parse(self) -> FormData:
        try:
            form = await super().parse()
            if not self._finished:
                raise MultiPartException("Incomplete multipart upload")
            return form
        except BaseException:
            # Includes not-yet-completed parts, not just files in FormData.
            for file in self._files_to_close_on_error:
                file.close()
            raise


class _ImportUploadRequest(Request):
    async def _get_form(
        self, *, max_files: int | float = 1000, max_fields: int | float = 1000,
        max_part_size: int = 1024 * 1024,
    ) -> FormData:
        if self._form is None:
            self._form = await _ClosingMultipartParser(
                self.headers, self.stream(), max_files=max_files,
                max_fields=max_fields, max_part_size=max_part_size,
            ).parse()
        return self._form


@router.post(
    "/{symbol}/import-json", response_model=FundamentalSyncView,
    openapi_extra={"requestBody": {"required": True, "content": {
        "multipart/form-data": {"schema": {
            "type": "object", "required": ["submissions", "companyfacts"],
            "additionalProperties": False,
            "properties": {
                "submissions": {"type": "string", "format": "binary"},
                "companyfacts": {"type": "string", "format": "binary"},
            },
        }},
    }}},
)
async def import_fundamentals_json(
    request: Request,
    symbol: str,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FundamentalSyncView:
    # No File/Form dependencies: security must run BEFORE Starlette spools data.
    require_local_request(request, allowed_origins=settings.cors_origins)
    max_file_bytes = max(0, settings.sec_import_max_file_mb * 1024 * 1024)
    _validate_import_headers(request, max_file_bytes)
    request = _ImportUploadRequest(request.scope, request.receive)
    try:
        async with request.form(max_files=2, max_fields=0) as form:
            parts = form.multi_items()
            if (
                len(parts) != 2
                or {name for name, _ in parts} != {"submissions", "companyfacts"}
                or any(not isinstance(upload, UploadFile) for _, upload in parts)
            ):
                raise HTTPException(status_code=400, detail="Exactly submissions and companyfacts files are required")
            submissions, companyfacts = form["submissions"], form["companyfacts"]
            for upload in (submissions, companyfacts):
                if upload.size is not None and upload.size > max_file_bytes:
                    raise SecImportFileTooLargeError("SEC JSON file exceeds the configured limit")
            submissions_bytes = await _read_import_upload(submissions, max_file_bytes)
            companyfacts_bytes = await _read_import_upload(companyfacts, max_file_bytes)
            # Decode, parse, validate, query and commit sequentially in ONE worker
            # invocation. The event loop never uses the SQLAlchemy session.
            result = await run_in_threadpool(
                SecManualJsonImportService(session, max_file_mb=settings.sec_import_max_file_mb).import_bytes,
                symbol=symbol, submissions=submissions_bytes, companyfacts=companyfacts_bytes,
                submissions_filename=submissions.filename, companyfacts_filename=companyfacts.filename,
            )
            return FundamentalSyncView.model_validate(result)
    except SecImportError as error:
        error_status = 422
        if isinstance(error, SecImportFileTooLargeError):
            error_status = 413
        elif isinstance(error, SecImportInvalidJsonError):
            error_status = 400
        elif isinstance(error, SecImportIdentityConflictError):
            error_status = 409
        elif isinstance(error, SecImportTransactionFailedError):
            error_status = 500
        raise HTTPException(status_code=error_status, detail={
            "code": error.code, "provider": "sec_edgar", "message": str(error),
        }) from None
    except (MultiPartException, MultipartParseError):
        raise HTTPException(status_code=400, detail="Invalid multipart upload") from None
    except StarletteHTTPException as error:
        # Starlette converts parser errors to HTTPException; do not echo raw
        # multipart header values or filenames that might be embedded in them.
        if error.status_code == 400:
            raise HTTPException(status_code=400, detail="Invalid multipart upload") from None
        raise
    except Exception:
        raise HTTPException(status_code=500, detail={
            "code": "sec_import_transaction_failed", "provider": "sec_edgar",
            "message": "SEC JSON import failed",
        }) from None
