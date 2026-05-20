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
