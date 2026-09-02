from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.portfolio import (
    AssetNotFoundError,
    DuplicatePositionError,
    PortfolioDomainError,
    PortfolioNotFoundError,
    PortfolioPersistenceError,
    PortfolioService,
    PortfolioValidationError,
    PositionNotFoundError,
)
from app.schemas import (
    PortfolioCreate,
    PortfolioDetail,
    PortfolioRead,
    PortfolioUpdate,
    PositionCreate,
    PositionRead,
    PositionUpdate,
)

router = APIRouter(prefix="/portfolios", tags=["portfolios"])
ResultT = TypeVar("ResultT")


def _http_error(error: PortfolioDomainError) -> HTTPException:
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
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Portfolio operation failed",
    )


def _run(operation: Callable[[], ResultT]) -> ResultT:
    try:
        return operation()
    except PortfolioDomainError as error:
        raise _http_error(error) from error


@router.get("", response_model=list[PortfolioRead])
def list_portfolios(db: Session = Depends(get_db)) -> list[PortfolioRead]:
    portfolios = PortfolioService(db).list_portfolios()
    return [PortfolioRead.model_validate(portfolio) for portfolio in portfolios]


@router.post("", response_model=PortfolioRead, status_code=status.HTTP_201_CREATED)
def create_portfolio(
    payload: PortfolioCreate,
    db: Session = Depends(get_db),
) -> PortfolioRead:
    portfolio = _run(lambda: PortfolioService(db).create_portfolio(**payload.model_dump()))
    return PortfolioRead.model_validate(portfolio)


@router.get("/{portfolio_id}", response_model=PortfolioDetail)
def get_portfolio(portfolio_id: int, db: Session = Depends(get_db)) -> PortfolioDetail:
    portfolio = _run(lambda: PortfolioService(db).get_portfolio(portfolio_id))
    return PortfolioDetail.model_validate(portfolio)


@router.patch("/{portfolio_id}", response_model=PortfolioRead)
def update_portfolio(
    portfolio_id: int,
    payload: PortfolioUpdate,
    db: Session = Depends(get_db),
) -> PortfolioRead:
    portfolio = _run(lambda: PortfolioService(db).update_portfolio(
        portfolio_id,
        payload.model_dump(exclude_unset=True),
    ))
    return PortfolioRead.model_validate(portfolio)


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio(portfolio_id: int, db: Session = Depends(get_db)) -> Response:
    _run(lambda: PortfolioService(db).delete_portfolio(portfolio_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{portfolio_id}/positions", response_model=list[PositionRead])
def list_positions(portfolio_id: int, db: Session = Depends(get_db)) -> list[PositionRead]:
    positions = _run(lambda: PortfolioService(db).list_positions(portfolio_id))
    return [PositionRead.model_validate(position) for position in positions]


@router.post(
    "/{portfolio_id}/positions",
    response_model=PositionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_position(
    portfolio_id: int,
    payload: PositionCreate,
    db: Session = Depends(get_db),
) -> PositionRead:
    position = _run(lambda: PortfolioService(db).create_position(
        portfolio_id,
        **payload.model_dump(),
    ))
    return PositionRead.model_validate(position)


@router.get("/{portfolio_id}/positions/{position_id}", response_model=PositionRead)
def get_position(
    portfolio_id: int,
    position_id: int,
    db: Session = Depends(get_db),
) -> PositionRead:
    position = _run(lambda: PortfolioService(db).get_position(portfolio_id, position_id))
    return PositionRead.model_validate(position)


@router.patch("/{portfolio_id}/positions/{position_id}", response_model=PositionRead)
def update_position(
    portfolio_id: int,
    position_id: int,
    payload: PositionUpdate,
    db: Session = Depends(get_db),
) -> PositionRead:
    position = _run(lambda: PortfolioService(db).update_position(
        portfolio_id,
        position_id,
        payload.model_dump(exclude_unset=True),
    ))
    return PositionRead.model_validate(position)


@router.delete(
    "/{portfolio_id}/positions/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_position(
    portfolio_id: int,
    position_id: int,
    db: Session = Depends(get_db),
) -> Response:
    _run(lambda: PortfolioService(db).delete_position(portfolio_id, position_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
