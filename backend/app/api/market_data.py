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
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderSymbolNotFoundError,
    ProviderTimeoutError,
    Timeframe,
)
from app.modules.data_sources.sync import synchronize_market_data
from app.repositories import MarketDataRepository
from app.schemas.market_data import (
    AssetView,
    LatestMarketView,
    MarketBarView,
    MarketHistoryView,
    MarketSyncView,
    QuoteView,
)

router = APIRouter(tags=["market data"])
TICKER_PATTERN = re.compile(r"^[A-Z0-9.\-]{1,16}$")
PROVIDER_PATTERN = re.compile(r"^[a-z0-9_\-]{1,40}$")
SUPPORTED_PROVIDERS = {"demo", "alpha_vantage"}


def get_market_data_provider(settings: Annotated[Settings, Depends(get_settings)]) -> MarketDataProvider:
    provider_name = _provider_name(settings.market_data_provider)
    if provider_name == "alpha_vantage":
        key = settings.alpha_vantage_api_key.get_secret_value() if settings.alpha_vantage_api_key else ""
        return AlphaVantageMarketDataProvider(
            api_key=key,
            base_url=settings.alpha_vantage_base_url,
            timeout_seconds=settings.market_data_timeout_seconds,
        )
    if provider_name == "demo":
        return DemoMarketDataProvider()
    raise ProviderConfigurationError(f"Unsupported market data provider: {provider_name}")


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


@router.post("/market/{symbol}/sync", response_model=MarketSyncView)
async def sync_market_data(
    symbol: str,
    session: Annotated[Session, Depends(get_db)],
    provider: Annotated[MarketDataProvider, Depends(get_market_data_provider)],
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
    try:
        result = await synchronize_market_data(
            session, provider, normalized, start_date, end_date, timeframe,
        )
    except ProviderTimeoutError as error:
        session.rollback()
        raise HTTPException(status_code=504, detail=str(error)) from error
    except ProviderRateLimitError as error:
        session.rollback()
        raise HTTPException(status_code=429, detail=str(error)) from error
    except ProviderSymbolNotFoundError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ProviderConfigurationError, MarketDataProviderError) as error:
        session.rollback()
        raise HTTPException(status_code=503, detail=str(error)) from error
    return MarketSyncView(
        symbol=result.symbol,
        provider=result.provider,
        inserted=result.inserted,
        updated=result.updated,
        rejected=result.rejected,
    )
