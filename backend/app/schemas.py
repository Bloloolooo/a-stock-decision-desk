from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class PositionCreate(BaseModel):
    symbol: str
    name: str
    quantity: int = Field(ge=0)
    average_cost: float = Field(gt=0)
    note: str = ""


class Position(PositionCreate):
    last_price: float
    market_value: float
    floating_pnl: float
    floating_pnl_pct: float
    updated_at: datetime


class CashUpdate(BaseModel):
    cash: float = Field(ge=0)


class PortfolioSummary(BaseModel):
    total_assets: float
    cash: float
    position_market_value: float
    floating_pnl: float
    today_pnl: float
    updated_at: datetime


class PriceBar(BaseModel):
    symbol: str
    period: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    turnover_rate: float | None = None
    adjust: str = "qfq"
    updated_at: datetime


class RiskAdvice(BaseModel):
    symbol: str
    name: str
    current_price: float
    position_ratio: float
    suggested_min_ratio: float
    suggested_max_ratio: float
    max_buy_amount: float
    stop_loss_price: float
    single_stock_risk: float
    message: str
    signal_sources: list[str]
    kelly_enabled: bool
    updated_at: datetime


class ScreenerResult(BaseModel):
    list_type: Literal["trend", "rebound"]
    symbol: str
    name: str
    score: int
    change_pct: float
    reason: str
    risk_status: str
    generated_at: datetime
