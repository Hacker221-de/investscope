import re
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.time import utc_now
from app.modules.data_sources import (
    AlphaVantageMarketDataProvider,
    DemoMarketDataProvider,
    MarketDataProvider,
    MarketDataProviderError,
    ProviderBurstLimitError,
    ProviderConfigurationError,
    ProviderDailyLimitError,
    ProviderInvalidRequestError,
    ProviderRateLimitError,
    ProviderSymbolNotFoundError,
    ProviderTimeoutError,
    Timeframe,
)
from app.modules.data_sources.gateway import AlphaVantageRequestGateway
from app.modules.data_sources.limits import ProviderBudget, ProviderRequestCoordinator
from app.modules.data_sources.sync import synchronize_market_data
from app.repositories import MarketDataRepository
from app.schemas.market_data import (
    AssetView,
    LatestMarketView,
    MarketBarView,
    MarketHistoryView,
    MarketSyncView,
    ProviderMarketDataStatusView,
    QuoteView,
)

router = APIRouter(tags=["market data"])
TICKER_PATTERN = re.compile(r"^[A-Z0-9.\-]{1,16}$")
PROVIDER_PATTERN = re.compile(r"^[a-z0-9_\-]{1,40}$")
SUPPORTED_PROVIDERS = {"demo", "alpha_vantage"}


def get_market_data_provider(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db)],
) -> MarketDataProvider:
    provider_name = _provider_name(settings.market_data_provider)
    if provider_name == "alpha_vantage":
        key = settings.alpha_vantage_api_key.get_secret_value() if settings.alpha_vantage_api_key else ""
        coordinator = ProviderRequestCoordinator(session, settings)
        gateway = AlphaVantageRequestGateway(
            api_key=key,
            base_url=settings.alpha_vantage_base_url,
            timeout_seconds=settings.market_data_timeout_seconds,
            coordinator=coordinator,
        )
        return AlphaVantageMarketDataProvider(gateway)
    if provider_name == "demo":
        return DemoMarketDataProvider()
    raise ProviderConfigurationError(f"Unsupported market data provider: {provider_name}")


def get_provider_request_coordinator(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProviderRequestCoordinator:
    return ProviderRequestCoordinator(session, settings)


def _symbol(value: str) -> str:
    normalized = value.upper()
    if not TICKER_PATTERN.fullmatch(normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ticker must contain only ASCII letters, digits, dot or hyphen",
        )
    return normalized


def _provider_name(value: str) -> str:
    normalized = value.strip().lower()
    if (
        not PROVIDER_PATTERN.fullmatch(normalized)
        or normalized not in SUPPORTED_PROVIDERS
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Provider must be one of: {', '.join(sorted(SUPPORTED_PROVIDERS))}",
        )
    return normalized


def _selected_provider(settings: Settings, override: str | None = None) -> str:
    return _provider_name(override or settings.market_data_provider)


def _stale(reference: datetime, settings: Settings) -> bool:
    return utc_now() - reference > timedelta(hours=settings.market_data_stale_after_hours)


def _quote(repository: MarketDataRepository, asset_id: int, currency: str,
           settings: Settings, provider: str) -> QuoteView | None:
    bars = repository.latest_two(asset_id, provider)
    if not bars or bars[0].close is None:
        return None
    latest = bars[0]
    previous = bars[1].close if len(bars) > 1 else None
    change = latest.close - previous if previous is not None else None
    change_percent = (
        change / previous * Decimal("100") if change is not None and previous != 0 else None
    )
    reference = latest.published_at or latest.event_time
    return QuoteView(
        close=latest.close, previous_close=previous, change=change,
        change_percent=change_percent, currency=currency, source=latest.provider,
        event_time=latest.event_time, published_at=latest.published_at,
        received_at=latest.received_at, is_stale=_stale(reference, settings),
    )


def _asset_view(
    repository: MarketDataRepository,
    asset: object,
    settings: Settings,
    provider: str,
) -> AssetView:
    view = AssetView.model_validate(asset)
    return view.model_copy(update={
        "latest_quote": _quote(repository, view.id, view.currency, settings, provider),
    })


def _sync_view(
    *,
    symbol: str,
    provider: str,
    inserted: int,
    updated: int,
    rejected: int,
    skipped: bool,
    skip_reason: str | None,
    budget: ProviderBudget,
    received_at: datetime,
    latest_event_time: datetime | None = None,
    latest_received_at: datetime | None = None,
) -> MarketSyncView:
    return MarketSyncView(
        provider=provider,
        symbol=symbol,
        inserted=inserted,
        updated=updated,
        rejected=rejected,
        skipped=skipped,
        reason=skip_reason,
        skip_reason=skip_reason,
        latest_event_time=latest_event_time,
        latest_received_at=latest_received_at,
        requests_used_today=budget.requests_used_today,
        daily_limit=budget.daily_limit,
        received_at=received_at,
    )


@router.get("/assets", response_model=list[AssetView])
def list_assets(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[AssetView]:
    repository = MarketDataRepository(session)
    provider = _selected_provider(settings)
    return [
        _asset_view(repository, asset, settings, provider)
        for asset in repository.list_assets()
    ]


@router.get("/assets/{symbol}", response_model=AssetView)
def asset_details(
    symbol: str,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssetView:
    repository = MarketDataRepository(session)
    asset = repository.get_asset(_symbol(symbol))
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return _asset_view(repository, asset, settings, _selected_provider(settings))


@router.get("/market/{symbol}/history", response_model=MarketHistoryView)
def market_history(
    symbol: str,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    start: date | None = None,
    end: date | None = None,
    timeframe: Timeframe = Timeframe.DAY_1,
    provider: Annotated[str | None, Query(max_length=40)] = None,
) -> MarketHistoryView:
    repository = MarketDataRepository(session)
    normalized = _symbol(symbol)
    asset = repository.get_asset(normalized)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    end_date = end or utc_now().date()
    start_date = start or end_date - timedelta(days=365)
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start must not be after end")
    selected_provider = _selected_provider(settings, provider)
    bars = repository.history(
        asset.id,
        datetime.combine(start_date, time.min, tzinfo=UTC),
        datetime.combine(end_date, time.max, tzinfo=UTC),
        timeframe,
        selected_provider,
    )
    return MarketHistoryView(
        symbol=normalized, timeframe=timeframe.value, provider=selected_provider,
        bars=[MarketBarView.model_validate(bar) for bar in bars],
    )


@router.get("/market/{symbol}/latest", response_model=LatestMarketView)
def latest_market_quote(
    symbol: str,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[str | None, Query(max_length=40)] = None,
) -> LatestMarketView:
    repository = MarketDataRepository(session)
    normalized = _symbol(symbol)
    asset = repository.get_asset(normalized)
    selected_provider = _selected_provider(settings, provider)
    quote = (
        _quote(repository, asset.id, asset.currency, settings, selected_provider)
        if asset is not None else None
    )
    if quote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No saved quote is available")
    return LatestMarketView(symbol=normalized, quote=quote)


@router.get("/providers/market-data/status", response_model=ProviderMarketDataStatusView)
def provider_market_data_status(
    settings: Annotated[Settings, Depends(get_settings)],
    coordinator: Annotated[
        ProviderRequestCoordinator, Depends(get_provider_request_coordinator)
    ],
) -> ProviderMarketDataStatusView:
    provider = _selected_provider(settings)
    budget = coordinator.budget(provider)
    if provider == "alpha_vantage":
        key_available = bool(
            settings.alpha_vantage_api_key
            and settings.alpha_vantage_api_key.get_secret_value()
        )
        usable_limit = max(
            (budget.daily_limit or 0) - settings.alpha_vantage_daily_reserve,
            0,
        )
        available = (
            key_available
            and budget.requests_used_today < usable_limit
            and budget.retry_after_seconds is None
        )
    else:
        available = True
    return ProviderMarketDataStatusView(
        configured_provider=provider,
        available=available,
        requests_used_today=budget.requests_used_today,
        daily_limit=budget.daily_limit,
        remaining_requests=budget.remaining_requests,
        last_request_at=budget.last_request_at,
        last_success_at=budget.last_success_at,
        last_error=budget.last_error,
        data_stale_after_hours=settings.market_data_stale_after_hours,
    )


@router.post("/market/{symbol}/sync", response_model=MarketSyncView)
async def sync_market_data(
    symbol: str,
    session: Annotated[Session, Depends(get_db)],
    provider: Annotated[MarketDataProvider, Depends(get_market_data_provider)],
    coordinator: Annotated[
        ProviderRequestCoordinator, Depends(get_provider_request_coordinator)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    start: Annotated[date | None, Query()] = None,
    end: Annotated[date | None, Query()] = None,
    timeframe: Timeframe = Timeframe.DAY_1,
) -> MarketSyncView:
    normalized = _symbol(symbol)
    end_date = end or utc_now().date()
    start_date = start or end_date - timedelta(days=100)
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start must not be after end")
    if end_date > utc_now().date():
        raise HTTPException(status_code=422, detail="future market data is not allowed")
    if (end_date - start_date).days > settings.market_sync_max_days:
        raise HTTPException(
            status_code=422,
            detail=f"date range cannot exceed {settings.market_sync_max_days} days",
        )
    repository = MarketDataRepository(session)
    asset = repository.get_asset(normalized)
    latest = repository.latest(asset.id, provider.name, timeframe) if asset is not None else None
    if latest is not None:
        reference = latest.published_at or latest.event_time
        if not _stale(reference, settings):
            return _sync_view(
                symbol=normalized,
                provider=provider.name,
                inserted=0,
                updated=0,
                rejected=0,
                skipped=True,
                skip_reason="fresh_data",
                budget=coordinator.budget(provider.name),
                received_at=utc_now(),
                latest_event_time=latest.event_time,
                latest_received_at=latest.received_at,
            )
    try:
        coordinator.ensure_capacity(provider.name, 2 if asset is not None else 3)
        result = await synchronize_market_data(
            session,
            provider,
            normalized,
            start_date,
            end_date,
            timeframe,
            coordinator,
        )
    except ProviderTimeoutError as error:
        session.rollback()
        raise HTTPException(status_code=504, detail=str(error)) from error
    except ProviderRateLimitError as error:
        session.rollback()
        budget = coordinator.budget(provider.name)
        requests_used = (
            error.requests_used_today
            if error.requests_used_today is not None
            else budget.requests_used_today
        )
        daily_limit = (
            error.daily_limit if error.daily_limit is not None else budget.daily_limit
        )
        if isinstance(error, ProviderBurstLimitError):
            error_code = "provider_burst_limit"
            message = "Действует временное ограничение частоты запросов"
        elif isinstance(error, ProviderDailyLimitError):
            error_code = "provider_daily_limit"
            message = (
                "Суточный лимит запросов провайдера исчерпан"
                if daily_limit is not None and requests_used >= daily_limit
                else "Действует временное ограничение частоты запросов"
            )
        else:
            error_code = "provider_rate_limit"
            message = "Провайдер временно ограничил запросы"
        raise HTTPException(
            status_code=429,
            detail={
                "code": error_code,
                "provider": provider.name,
                "message": message,
                "retry_after_seconds": error.retry_after_seconds,
                "requests_used_today": requests_used,
                "daily_limit": daily_limit,
            },
        ) from error
    except ProviderInvalidRequestError as error:
        session.rollback()
        raise HTTPException(
            status_code=502,
            detail={
                "code": "provider_invalid_request",
                "provider": provider.name,
                "message": "Провайдер отклонил параметры запроса",
            },
        ) from error
    except ProviderSymbolNotFoundError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ProviderConfigurationError, MarketDataProviderError) as error:
        session.rollback()
        raise HTTPException(status_code=503, detail=str(error)) from error
    latest = repository.latest(asset.id, provider.name, timeframe) if asset is not None else None
    if latest is None:
        refreshed_asset = repository.get_asset(normalized)
        latest = (
            repository.latest(refreshed_asset.id, provider.name, timeframe)
            if refreshed_asset is not None else None
        )
    return _sync_view(
        symbol=result.symbol,
        provider=result.provider,
        inserted=result.inserted,
        updated=result.updated,
        rejected=result.rejected,
        skipped=False,
        skip_reason=None,
        budget=coordinator.budget(provider.name),
        received_at=result.received_at,
        latest_event_time=latest.event_time if latest is not None else None,
        latest_received_at=latest.received_at if latest is not None else None,
    )
