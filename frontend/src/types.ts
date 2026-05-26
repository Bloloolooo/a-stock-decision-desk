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
  list_type: "trend" | "rebound";
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

export type IndicatorPoint = {
  timestamp: string;
  value?: number | null;
  signal?: number | null;
  histogram?: number | null;
  k?: number | null;
  d?: number | null;
  j?: number | null;
};

export type ChipLevel = {
  price: number;
  volume_ratio: number;
  label: string;
};

export type DecisionCenter = {
  symbol: string;
  name: string;
  current_price: number;
  trend_status: string;
  volume_status: string;
  volume_ratio: number;
  turnover_rate?: number | null;
  support_price: number;
  resistance_price: number;
  macd_status: string;
  kdj_status: string;
  intraday_game: {
    status: string;
    buy_power_pct: number;
    sell_power_pct: number;
    vwap: number;
    price_vs_vwap_pct: number;
    description: string;
  };
  chips: ChipLevel[];
  macd: IndicatorPoint[];
  kdj: IndicatorPoint[];
  advice: {
    action: string;
    confidence: number;
    reasons: string[];
    warnings: string[];
  };
  updated_at: string;
};
