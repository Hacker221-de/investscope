import csv
from datetime import date
from decimal import Decimal
from io import StringIO
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.time import utc_now
from app.demo_data import ASSETS, POLITICAL_EVENTS, RECOMMENDATIONS
from app.modules.backtesting import fixed_demo_series, sma_crossover_analysis
from app.modules.data_sources import DemoMarketDataSource
from app.modules.portfolio import (
    AssetNotFoundError,
    DuplicatePositionError,
    OwnedPosition,
    PortfolioDomainError,
    PortfolioNotFoundError,
    PortfolioPersistenceError,
    PortfolioService,
    PortfolioValidationError,
    PositionNotFoundError,
    analyze_portfolio,
)
from app.repositories import MarketDataRepository
from app.schemas import (
    AssetDetail,
    AssetSummary,
    BacktestRequest,
    BacktestResult,
    CSVImportResult,
    DashboardSummary,
    LegacyPositionCreate,
    LegacyPositionUpdate,
    PositionView,
    PoliticalEventView,
    PortfolioView,
    RecommendationView,
)

router = APIRouter()
market_data = DemoMarketDataSource()


def _asset_metadata(symbol: str) -> dict[str, Any]:
    asset = next((item for item in ASSETS if item["symbol"] == symbol.upper()), None)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"No analytical market data is available for symbol {symbol.upper()}",
        )
    return asset


def _portfolio_http_error(error: PortfolioDomainError) -> HTTPException:
    if isinstance(error, (PortfolioNotFoundError, PositionNotFoundError, AssetNotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, DuplicatePositionError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, PortfolioValidationError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    if isinstance(error, PortfolioPersistenceError):
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Portfolio storage operation failed",
        )
    return HTTPException(status_code=500, detail="Portfolio operation failed")


def _first_portfolio(service: PortfolioService):
    portfolios = service.list_portfolios()
    if not portfolios:
        raise PortfolioNotFoundError("Portfolio not found")
    return service.get_portfolio(portfolios[0].id)


def _owned_positions(
    db: Session,
    service: PortfolioService,
    portfolio_id: int,
    provider: str,
) -> list[OwnedPosition]:
    result: list[OwnedPosition] = []
    market_repository = MarketDataRepository(db)
    for position in service.list_positions(portfolio_id):
        asset = position.asset
        quote = market_repository.latest(asset.id, provider)
        result.append(
            OwnedPosition(
                id=position.id,
                symbol=asset.symbol,
                quantity=position.quantity,
                average_purchase_price=position.average_purchase_price,
                purchase_date=position.purchase_date,
                currency=position.currency,
                fees=position.fees,
                sector=asset.sector or "Unknown",
                geography="Unknown",
                current_price=quote.close if quote is not None else None,
                price_source=quote.provider if quote is not None else None,
                price_updated_at=quote.received_at if quote is not None else None,
            )
        )
    return result


def _portfolio_view(db: Session, settings: Settings) -> PortfolioView:
    service = PortfolioService(db)
    portfolio = _first_portfolio(service)
    analysis = analyze_portfolio(
        name=portfolio.name,
        base_currency=portfolio.base_currency,
        positions=_owned_positions(
            db,
            service,
            portfolio.id,
            settings.market_data_provider,
        ),
        as_of=utc_now(),
    )
    return PortfolioView.model_validate(analysis)


def _view_for_id(
    db: Session,
    settings: Settings,
    position_id: int,
) -> PositionView:
    view = next(
        (
            position
            for position in _portfolio_view(db, settings).positions
            if position.id == position_id
        ),
        None,
    )
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")
    return view


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DashboardSummary:
    try:
        portfolio = _portfolio_view(db, settings)
    except PortfolioNotFoundError:
        portfolio = None
    return DashboardSummary(
        portfolio_value=portfolio.current_value if portfolio else Decimal("0"),
        invested_capital=portfolio.invested_capital if portfolio else Decimal("0"),
        unrealized_pnl=portfolio.unrealized_pnl if portfolio else Decimal("0"),
        total_return_percent=portfolio.total_return_percent if portfolio else Decimal("0"),
        active_recommendations=len(RECOMMENDATIONS),
        high_impact_events=sum(event["impact"] == "high" for event in POLITICAL_EVENTS),
        market_status="DEMO MARKET DATA",
    )


@router.get("/assets", response_model=list[AssetSummary])
def list_assets() -> list[AssetSummary]:
    return [AssetSummary.model_validate(asset) for asset in ASSETS]


@router.get("/assets/{symbol}", response_model=AssetDetail)
def asset_detail(symbol: str) -> AssetDetail:
    asset = next((item for item in ASSETS if item["symbol"] == symbol.upper()), None)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return AssetDetail.model_validate(asset)


@router.get("/recommendations", response_model=list[RecommendationView])
def list_recommendations() -> list[RecommendationView]:
    return [RecommendationView.model_validate(item) for item in RECOMMENDATIONS]


@router.get("/portfolio", response_model=PortfolioView)
def get_portfolio(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PortfolioView:
    try:
        return _portfolio_view(db, settings)
    except PortfolioDomainError as error:
        raise _portfolio_http_error(error) from error


@router.post("/portfolio/positions", response_model=PositionView, status_code=status.HTTP_201_CREATED)
def create_position(
    position: LegacyPositionCreate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PositionView:
    service = PortfolioService(db)
    try:
        portfolio = _first_portfolio(service)
        asset = service.repository.get_asset_by_symbol(position.symbol)
        if asset is None:
            raise AssetNotFoundError("Asset not found")
        created = service.create_position(
            portfolio.id,
            asset_id=asset.id,
            quantity=position.quantity,
            average_purchase_price=position.average_purchase_price,
            purchase_date=position.purchase_date,
            currency=position.currency,
            fees=position.fees,
        )
        return _view_for_id(db, settings, created.id)
    except PortfolioDomainError as error:
        raise _portfolio_http_error(error) from error


@router.patch("/portfolio/positions/{position_id}", response_model=PositionView)
def update_position(
    position_id: int,
    update: LegacyPositionUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PositionView:
    service = PortfolioService(db)
    try:
        portfolio = _first_portfolio(service)
        existing = service.get_position(portfolio.id, position_id)
        changes = update.model_dump(exclude_unset=True)
        requested_symbol = changes.pop("symbol", existing.symbol)
        if requested_symbol is None or requested_symbol.upper() != existing.symbol:
            raise PortfolioValidationError(
                "Asset cannot be changed; delete the position and create a new one"
            )
        service.update_position(portfolio.id, position_id, changes)
        return _view_for_id(db, settings, position_id)
    except PortfolioDomainError as error:
        raise _portfolio_http_error(error) from error


@router.delete("/portfolio/positions/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_position(position_id: int, db: Session = Depends(get_db)) -> Response:
    service = PortfolioService(db)
    try:
        portfolio = _first_portfolio(service)
        service.delete_position(portfolio.id, position_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PortfolioDomainError as error:
        raise _portfolio_http_error(error) from error


@router.post("/portfolio/import-csv", response_model=CSVImportResult)
async def import_positions_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CSVImportResult:
    if file.size is not None and file.size > 1_000_000:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="CSV is too large")
    try:
        content = (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV must be UTF-8") from error

    reader = csv.DictReader(StringIO(content))
    required = {"symbol", "quantity", "average_purchase_price", "purchase_date", "currency"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV must contain columns: {', '.join(sorted(required))}; fees is optional",
        )

    service = PortfolioService(db)
    try:
        portfolio = _first_portfolio(service)
    except PortfolioDomainError as error:
        raise _portfolio_http_error(error) from error
    imported_ids: list[int] = []
    errors: list[str] = []
    for row_number, row in enumerate(reader, start=2):
        try:
            payload = LegacyPositionCreate(
                symbol=row["symbol"],
                quantity=Decimal(row["quantity"]),
                average_purchase_price=Decimal(row["average_purchase_price"]),
                purchase_date=date.fromisoformat(row["purchase_date"]),
                currency=row["currency"],
                fees=Decimal(row["fees"]) if row.get("fees") else None,
            )
            asset = service.repository.get_asset_by_symbol(payload.symbol)
            if asset is None:
                raise AssetNotFoundError("Asset not found")
            created = service.create_position(
                portfolio.id,
                asset_id=asset.id,
                quantity=payload.quantity,
                average_purchase_price=payload.average_purchase_price,
                purchase_date=payload.purchase_date,
                currency=payload.currency,
                fees=payload.fees,
            )
            imported_ids.append(created.id)
        except (
            ValidationError,
            ValueError,
            ArithmeticError,
            HTTPException,
            PortfolioDomainError,
        ) as error:
            errors.append(f"row {row_number}: {error}")

    all_positions = _portfolio_view(db, settings).positions
    return CSVImportResult(
        imported_count=len(imported_ids),
        positions=[position for position in all_positions if position.id in imported_ids],
        errors=errors,
    )


@router.get("/political-events", response_model=list[PoliticalEventView])
def list_political_events() -> list[PoliticalEventView]:
    return [PoliticalEventView.model_validate(item) for item in POLITICAL_EVENTS]


@router.post("/backtesting/run", response_model=BacktestResult)
def run_backtest(request: BacktestRequest) -> BacktestResult:
    if market_data.price_for(request.symbol) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    try:
        dates, demo_prices = fixed_demo_series(request.start_date, request.end_date)
        result = sma_crossover_analysis(
            demo_prices,
            request.initial_capital,
            request.short_window,
            request.long_window,
            request.method,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    return BacktestResult(
        symbol=request.symbol.upper(),
        method=request.method,
        start_date=request.start_date,
        end_date=request.end_date,
        final_value=result["final_value"],
        benchmark_final_value=result["benchmark_final_value"],
        total_return_percent=result["total_return_percent"],
        benchmark_return_percent=result["benchmark_return_percent"],
        max_drawdown_percent=result["max_drawdown_percent"],
        sharpe_ratio=result["sharpe_ratio"],
        signals=int(result["signals"]),
        correct_signals=int(result["correct_signals"]),
        incorrect_signals=int(result["incorrect_signals"]),
        dates=dates,
        strategy_curve=result["strategy_curve"],
        benchmark_curve=result["benchmark_curve"],
        note="Deterministic analytical SMA test on a fixed demo series; no orders or executions.",
    )
