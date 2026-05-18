from fastapi import APIRouter

from app.schemas import CashUpdate, PortfolioSummary, Position, PositionCreate
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


@router.post("/positions", response_model=Position)
def upsert_position(payload: PositionCreate) -> Position:
    return portfolio_service.upsert_position(payload)
