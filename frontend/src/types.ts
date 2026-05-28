export type Position = {
  symbol: string;
  name: string;
  quantity: number;
  average_cost: number;
  last_price: number;
  market_value: number;
  floating_pnl: number;
  floating_pnl_pct: number;
  updated_at: string;
};

export type PositionInput = {
  symbol: string;
  name?: string;
  quantity: number;
  average_cost: number;
  note?: string;
};

export type WatchItem = {
  symbol: string;
  name: string;
  tags: string;
  note: string;
  last_price: number;
  created_at: string;
  updated_at: string;
};

export type WatchItemInput = {
  symbol: string;
  name?: string;
  tags?: string;
  note?: string;
};

export type SellInput = {
  symbol: string;
  quantity: number;
  sell_price: number;
  note?: string;
};

export type PortfolioSummary = {
  total_assets: number;
  cash: number;
  position_market_value: number;
  floating_pnl: number;
  today_pnl: number;
  updated_at: string;
};

export type PriceBar = {
  symbol: string;
  period: string;
  trade_date: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
};

export type MarketStatus = {
  provider: string;
  active_source: string;
  description: string;
  last_error?: string | null;
  updated_at: string;
};

export type MarketSettings = {
  provider: string;
  tushare_token_configured: boolean;
  updated_at: string;
};

export type MarketPeriod = {
  key: string;
  label: string;
  description: string;
  available: boolean;
};

export type RiskAdvice = {
  symbol: string;
  name: string;
  current_price: number;
  position_ratio: number;
  suggested_min_ratio: number;
  suggested_max_ratio: number;
  max_buy_amount: number;
  stop_loss_price: number;
  atr_multiplier: number;
  market_regime: string;
  take_profit_1?: number | null;
  take_profit_2?: number | null;
  trailing_stop?: number | null;
  single_stock_risk: number;
  message: string;
  signal_sources: string[];
  action_suggestions: string[];
  kelly_enabled: boolean;
  updated_at: string;
};

export type TradeRecord = {
  id: number;
  symbol: string;
  name: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  amount: number;
  note: string;
  created_at: string;
};

export type ScreenerResult = {
  list_type: "balanced" | "trend" | "rebound";
  symbol: string;
  name: string;
  score: number;
  change_pct: number;
  reason: string;
  risk_status: string;
  factors: Array<{
    name: string;
    value: string;
    contribution: number;
    status: string;
  }>;
  generated_at: string;
};

export type ScreenerConfig = {
  symbols: string[];
  updated_at: string;
};

export type ScreenerStatus = {
  pool_size: number;
  cache_age_seconds?: number | null;
  last_scan_at?: string | null;
  last_duration_seconds?: number | null;
  last_error_count: number;
  symbols: string[];
  scan_status: string;
  scope: string;
  total_count: number;
  processed_count: number;
  success_count: number;
  market_environment: string;
  market_factor: number;
  last_error?: string | null;
};

export type PredictionStatus = {
  enabled: boolean;
  model_name: string;
  tokenizer_name: string;
  install_status: "not_installed" | "installing" | "ready" | "failed" | string;
  last_error?: string | null;
  installed_at?: string | null;
  updated_at: string;
  runtime_path: string;
  ready: boolean;
  install_commands: string[];
  environment_checks: string[];
};

export type PredictionResult = {
  symbol: string;
  name: string;
  model_name: string;
  horizon: number;
  history: PriceBar[];
  forecast: PriceBar[];
  expected_change_pct: number;
  generated_at: string;
  message: string;
};

export type BacktestRequest = {
  symbol: string;
  initial_cash: number;
  buy_threshold: number;
  sell_threshold: number;
  atr_multiplier: number;
  max_position_ratio: number;
  commission_rate: number;
  stamp_tax_rate: number;
  slippage_rate: number;
};

export type BacktestTrade = {
  trade_date: string;
  side: "buy" | "sell";
  price: number;
  quantity: number;
  amount: number;
  fee: number;
  reason: string;
  confidence: number;
  pnl?: number | null;
  pnl_pct?: number | null;
};

export type BacktestEquityPoint = {
  trade_date: string;
  equity: number;
  cash: number;
  position_value: number;
  drawdown_pct: number;
  confidence: number;
};

export type BacktestResult = {
  symbol: string;
  name: string;
  start_date: string;
  end_date: string;
  initial_cash: number;
  final_equity: number;
  total_return_pct: number;
  annual_return_pct: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  win_rate: number;
  win_loss_ratio: number;
  trade_count: number;
  average_holding_days: number;
  estimated_kelly_ratio: number;
  cost_total: number;
  trades: BacktestTrade[];
  equity_curve: BacktestEquityPoint[];
  summary: string;
};

export type IndicatorPoint = {
  timestamp: string;
  value?: number | null;
  signal?: number | null;
  histogram?: number | null;
  k?: number | null;
  d?: number | null;
  j?: number | null;
  pdi?: number | null;
  mdi?: number | null;
  adx?: number | null;
};

export type ChipLevel = {
  price: number;
  volume_ratio: number;
  label: string;
};

export type ChipAnalysis = {
  status: string;
  support_strength: number;
  pressure_strength: number;
  nearest_support?: number | null;
  nearest_pressure?: number | null;
  description: string;
};

export type IndicatorScore = {
  group: string;
  name: string;
  status: string;
  value: string;
  contribution: number;
};

export type TradingPlan = {
  market_regime: string;
  atr: number;
  atr_multiplier: number;
  buy_support_price: number;
  buy_pullback_price: number;
  buy_breakout_price: number;
  stop_loss_price: number;
  take_profit_1: number;
  take_profit_2: number;
  trailing_stop: number;
  risk_reward_ratio: number;
  expectancy: number;
  plan_summary: string;
};

export type DecisionCenter = {
  symbol: string;
  name: string;
  current_price: number;
  trend_status: string;
  volume_status: string;
  volume_ratio: number;
  turnover_rate?: number | null;
  market_regime: string;
  support_price: number;
  resistance_price: number;
  macd_status: string;
  kdj_status: string;
  rsi_status: string;
  wr_status: string;
  psy_status: string;
  dmi_status: string;
  intraday_game: {
    status: string;
    buy_power_pct: number;
    sell_power_pct: number;
    vwap: number;
    price_vs_vwap_pct: number;
    description: string;
  };
  chips: ChipLevel[];
  chip_analysis: ChipAnalysis;
  macd: IndicatorPoint[];
  kdj: IndicatorPoint[];
  rsi: IndicatorPoint[];
  wr: IndicatorPoint[];
  psy: IndicatorPoint[];
  dmi: IndicatorPoint[];
  indicator_matrix: IndicatorScore[];
  trading_plan: TradingPlan;
  advice: {
    action: string;
    confidence: number;
    reasons: string[];
    warnings: string[];
  };
  updated_at: string;
};

export type DashboardData = {
  symbol: string;
  period: string;
  bars: PriceBar[];
  risk: RiskAdvice;
  decision: DecisionCenter;
  market_status: MarketStatus;
  updated_at: string;
};
