from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class PositionCreate(BaseModel):
    symbol: str
    name: str = ""
    quantity: int = Field(ge=0)
    average_cost: float = Field(gt=0)
    note: str = ""


class PositionSell(BaseModel):
    symbol: str
    quantity: int = Field(gt=0)
    sell_price: float = Field(gt=0)
    note: str = ""


class TradeRecord(BaseModel):
    id: int
    symbol: str
    name: str
    side: Literal["buy", "sell"]
    quantity: int
    price: float
    amount: float
    note: str = ""
    created_at: datetime


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
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    turnover_rate: float | None = None
    adjust: str = "qfq"
    updated_at: datetime


class StockInfo(BaseModel):
    symbol: str
    name: str


class MarketStatus(BaseModel):
    provider: str
    active_source: str
    description: str
    last_error: str | None = None
    updated_at: datetime


class MarketSettings(BaseModel):
    provider: str
    tushare_token_configured: bool = False
    updated_at: datetime


class MarketSettingsUpdate(BaseModel):
    provider: str
    tushare_token: str = ""


class MarketPeriod(BaseModel):
    key: str
    label: str
    description: str
    available: bool = True


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
    action_suggestions: list[str]
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
    factors: list[dict[str, str | int | float]]
    generated_at: datetime


class ScreenerConfig(BaseModel):
    symbols: list[str]
    updated_at: datetime


class ScreenerConfigUpdate(BaseModel):
    symbols: list[str]


class ScreenerStatus(BaseModel):
    pool_size: int
    cache_age_seconds: int | None = None
    last_scan_at: datetime | None = None
    last_duration_seconds: float | None = None
    last_error_count: int = 0
    symbols: list[str]


class PredictionSettings(BaseModel):
    enabled: bool
    model_name: str
    tokenizer_name: str
    install_status: str
    last_error: str | None = None
    installed_at: datetime | None = None
    updated_at: datetime


class PredictionSettingsUpdate(BaseModel):
    enabled: bool
    model_name: str = "NeoQuasar/Kronos-small"


class PredictionStatus(PredictionSettings):
    runtime_path: str
    ready: bool


class PredictionResult(BaseModel):
    symbol: str
    name: str
    model_name: str
    horizon: int
    history: list[PriceBar]
    forecast: list[PriceBar]
    expected_change_pct: float
    generated_at: datetime
    message: str


class IndicatorPoint(BaseModel):
    timestamp: str
    value: float | None = None
    signal: float | None = None
    histogram: float | None = None
    k: float | None = None
    d: float | None = None
    j: float | None = None


class ChipLevel(BaseModel):
    price: float
    volume_ratio: float
    label: str


class IntradayGame(BaseModel):
    status: str
    buy_power_pct: float
    sell_power_pct: float
    vwap: float
    price_vs_vwap_pct: float
    description: str


class DecisionAdvice(BaseModel):
    action: str
    confidence: int
    reasons: list[str]
    warnings: list[str]


class DecisionCenter(BaseModel):
    symbol: str
    name: str
    current_price: float
    trend_status: str
    volume_status: str
    volume_ratio: float
    turnover_rate: float | None = None
    support_price: float
    resistance_price: float
    macd_status: str
    kdj_status: str
    intraday_game: IntradayGame
    chips: list[ChipLevel]
    macd: list[IndicatorPoint]
    kdj: list[IndicatorPoint]
    advice: DecisionAdvice
    updated_at: datetime
