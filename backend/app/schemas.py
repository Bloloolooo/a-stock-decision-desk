from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class PositionCreate(BaseModel):
    symbol: str
    name: str = ""
    quantity: int = Field(gt=0)
    average_cost: float = Field(gt=0)
    note: str = ""


class PositionSell(BaseModel):
    symbol: str
    quantity: int = Field(gt=0)
    sell_price: float = Field(gt=0)
    note: str = ""


class PositionNameUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=32)


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


class BacktestRequest(BaseModel):
    symbol: str
    start_date: date | None = None
    end_date: date | None = None
    initial_cash: float = Field(default=100000, gt=0)
    buy_threshold: int = Field(default=72, ge=0, le=100)
    sell_threshold: int = Field(default=45, ge=0, le=100)
    atr_multiplier: float = Field(default=2.0, gt=0)
    max_position_ratio: float = Field(default=0.35, gt=0, le=1)
    commission_rate: float = Field(default=0.0003, ge=0)
    stamp_tax_rate: float = Field(default=0.0005, ge=0)
    slippage_rate: float = Field(default=0.0005, ge=0)


class BacktestTrade(BaseModel):
    trade_date: date
    side: Literal["buy", "sell"]
    price: float
    quantity: int
    amount: float
    fee: float
    reason: str
    confidence: int
    pnl: float | None = None
    pnl_pct: float | None = None


class BacktestEquityPoint(BaseModel):
    trade_date: date
    equity: float
    cash: float
    position_value: float
    drawdown_pct: float
    confidence: int


class BacktestResult(BaseModel):
    symbol: str
    name: str
    start_date: date
    end_date: date
    initial_cash: float
    final_equity: float
    total_return_pct: float
    annual_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    win_rate: float
    win_loss_ratio: float
    trade_count: int
    average_holding_days: float
    estimated_kelly_ratio: float
    cost_total: float
    trades: list[BacktestTrade]
    equity_curve: list[BacktestEquityPoint]
    summary: str


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
    scan_status: str = "idle"
    scope: str = "default"
    total_count: int = 0
    processed_count: int = 0
    success_count: int = 0
    market_environment: str = "未知"
    market_factor: float = 1.0
    last_error: str | None = None


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
    pdi: float | None = None
    mdi: float | None = None
    adx: float | None = None


class ChipLevel(BaseModel):
    price: float
    volume_ratio: float
    label: str


class ChipAnalysis(BaseModel):
    status: str
    support_strength: float
    pressure_strength: float
    nearest_support: float | None = None
    nearest_pressure: float | None = None
    description: str


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


class IndicatorScore(BaseModel):
    group: str
    name: str
    status: str
    value: str
    contribution: int


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
    rsi_status: str
    wr_status: str
    psy_status: str
    dmi_status: str
    intraday_game: IntradayGame
    chips: list[ChipLevel]
    chip_analysis: ChipAnalysis
    macd: list[IndicatorPoint]
    kdj: list[IndicatorPoint]
    rsi: list[IndicatorPoint]
    wr: list[IndicatorPoint]
    psy: list[IndicatorPoint]
    dmi: list[IndicatorPoint]
    indicator_matrix: list[IndicatorScore]
    advice: DecisionAdvice
    updated_at: datetime


class DashboardData(BaseModel):
    symbol: str
    period: str
    bars: list[PriceBar]
    risk: RiskAdvice
    decision: DecisionCenter
    market_status: MarketStatus
    updated_at: datetime
