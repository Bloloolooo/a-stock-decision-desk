from fastapi import APIRouter, HTTPException

from app.schemas import CashUpdate, PortfolioSummary, Position, PositionCreate, PositionSell, TradeRecord
from app.services.portfolio import portfolio_service

router = APIRouter()


@router.get("/summary", response_model=PortfolioSummary)
def get_summary() -> PortfolioSummary:
    return portfolio_service.summary()


@router.post("/cash", response_model=PortfolioSummary)
def update_cash(payload: CashUpdate) -> PortfolioSummary:
    portfolio_service.set_cash(payload.cash)
    return portfolio_service.summary()


@router.get("/positions", response_model=list[Position])
def get_positions() -> list[Position]:
    return portfolio_service.positions()


@router.get("/trades", response_model=list[TradeRecord])
def get_trade_records(limit: int = 100) -> list[TradeRecord]:
    return portfolio_service.trade_records(limit=min(max(limit, 1), 300))


@router.post("/positions", response_model=Position)
def upsert_position(payload: PositionCreate) -> Position:
    try:
        return portfolio_service.upsert_position(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sell", response_model=PortfolioSummary)
def sell_position(payload: PositionSell) -> PortfolioSummary:
    try:
        portfolio_service.sell_position(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return portfolio_service.summary()
