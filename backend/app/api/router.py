import csv
from datetime import date
from decimal import Decimal
from io import StringIO
from typing import Any

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from pydantic import ValidationError

from app.core.time import utc_now
from app.demo_data import ASSETS, POLITICAL_EVENTS, PORTFOLIO, RECOMMENDATIONS
from app.modules.backtesting import backtest_summary
from app.modules.data_sources import DemoMarketDataSource
from app.modules.portfolio import OwnedPosition, analyze_portfolio
from app.schemas import (
    AssetDetail,
    AssetSummary,
    BacktestRequest,
    BacktestResult,
    CSVImportResult,
    DashboardSummary,
    PositionCreate,
    PositionUpdate,
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


def _owned_positions() -> list[OwnedPosition]:
    result: list[OwnedPosition] = []
    for raw in PORTFOLIO["positions"]:
        asset = _asset_metadata(raw["symbol"])
        result.append(
            OwnedPosition(
                id=raw["id"],
                symbol=raw["symbol"],
                quantity=raw["quantity"],
                average_purchase_price=raw["average_purchase_price"],
                purchase_date=raw["purchase_date"],
                currency=raw["currency"],
                fees=raw.get("fees"),
                sector=asset["sector"],
                geography=raw.get("geography", "Unknown"),
                current_price=asset["price"],
            )
        )
    return result


def _portfolio_view() -> PortfolioView:
    analysis = analyze_portfolio(
        name=PORTFOLIO["name"],
        base_currency=PORTFOLIO["base_currency"],
        positions=_owned_positions(),
        as_of=PORTFOLIO["as_of"],
    )
    return PortfolioView.model_validate(analysis)


def _append_position(position: PositionCreate) -> int:
    asset = _asset_metadata(position.symbol)
    raw_positions: list[dict[str, Any]] = PORTFOLIO["positions"]
    position_id = max((item["id"] for item in raw_positions), default=0) + 1
    raw_positions.append(
        {
            "id": position_id,
            **position.model_dump(),
            "sector": asset["sector"],
            "geography": "United States",
        }
    )
    PORTFOLIO["as_of"] = utc_now()
    return position_id


def _view_for_id(position_id: int) -> PositionView:
    view = next(
        (position for position in _portfolio_view().positions if position.id == position_id),
        None,
    )
    if view is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")
    return view


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard() -> DashboardSummary:
    portfolio = _portfolio_view()
    return DashboardSummary(
        portfolio_value=portfolio.current_value,
        invested_capital=portfolio.invested_capital,
        unrealized_pnl=portfolio.unrealized_pnl,
        total_return_percent=portfolio.total_return_percent,
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
def get_portfolio() -> PortfolioView:
    return _portfolio_view()


@router.post("/portfolio/positions", response_model=PositionView, status_code=status.HTTP_201_CREATED)
def create_position(position: PositionCreate) -> PositionView:
    return _view_for_id(_append_position(position))


@router.patch("/portfolio/positions/{position_id}", response_model=PositionView)
def update_position(position_id: int, update: PositionUpdate) -> PositionView:
    raw_positions: list[dict[str, Any]] = PORTFOLIO["positions"]
    position = next((item for item in raw_positions if item["id"] == position_id), None)
    if position is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")
    changes = update.model_dump(exclude_unset=True)
    if "symbol" in changes:
        asset = _asset_metadata(changes["symbol"])
        changes["sector"] = asset["sector"]
    position.update(changes)
    PORTFOLIO["as_of"] = utc_now()
    return _view_for_id(position_id)


@router.delete("/portfolio/positions/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_position(position_id: int) -> Response:
    raw_positions: list[dict[str, Any]] = PORTFOLIO["positions"]
    position = next((item for item in raw_positions if item["id"] == position_id), None)
    if position is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")
    raw_positions.remove(position)
    PORTFOLIO["as_of"] = utc_now()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/portfolio/import-csv", response_model=CSVImportResult)
async def import_positions_csv(file: UploadFile = File(...)) -> CSVImportResult:
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

    imported_ids: list[int] = []
    errors: list[str] = []
    for row_number, row in enumerate(reader, start=2):
        try:
            payload = PositionCreate(
                symbol=row["symbol"],
                quantity=Decimal(row["quantity"]),
                average_purchase_price=Decimal(row["average_purchase_price"]),
                purchase_date=date.fromisoformat(row["purchase_date"]),
                currency=row["currency"],
                fees=Decimal(row["fees"]) if row.get("fees") else None,
            )
            imported_ids.append(_append_position(payload))
        except (ValidationError, ValueError, ArithmeticError, HTTPException) as error:
            errors.append(f"row {row_number}: {error}")

    all_positions = _portfolio_view().positions
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
    demo_prices = [
        Decimal("100"),
        Decimal("104"),
        Decimal("102"),
        Decimal("108"),
        Decimal("111"),
        Decimal("107"),
        Decimal("115"),
    ]
    result = backtest_summary(demo_prices, request.initial_capital)
    return BacktestResult(
        symbol=request.symbol.upper(),
        total_return_percent=result["total_return_percent"],
        max_drawdown_percent=result["max_drawdown_percent"],
        sharpe_ratio=Decimal("1.31"),
        signals=int(result["signals"]),
        note="Illustrative result calculated from a fixed demo price series; not investment advice.",
    )
