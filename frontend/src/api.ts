import type { BacktestRequest, BacktestResult, DashboardData, DecisionCenter, MarketPeriod, MarketSettings, MarketStatus, PortfolioSummary, Position, PositionInput, PredictionResult, PredictionStatus, PriceBar, RiskAdvice, ScreenerConfig, ScreenerResult, ScreenerStatus, SellInput, TradeRecord, WatchItem, WatchItemInput } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api";

async function requestError(response: Response) {
  try {
    const payload = await response.json();
    const detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail ?? payload);
    return new Error(detail || `API request failed: ${response.status}`);
  } catch {
    return new Error(`API request failed: ${response.status}`);
  }
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw await requestError(response);
  }
  return response.json();
}

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await requestError(response);
  }
  return response.json();
}

async function putJson<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await requestError(response);
  }
  return response.json();
}

async function patchJson<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await requestError(response);
  }
  return response.json();
}

async function deleteJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw await requestError(response);
  }
  return response.json();
}

export const api = {
  summary: () => getJson<PortfolioSummary>("/portfolio/summary"),
  positions: () => getJson<Position[]>("/portfolio/positions"),
  watchlist: () => getJson<WatchItem[]>("/portfolio/watchlist"),
  trades: () => getJson<TradeRecord[]>("/portfolio/trades"),
  updateCash: (cash: number) => postJson<PortfolioSummary>("/portfolio/cash", { cash }),
  upsertPosition: (position: PositionInput) => postJson<Position>("/portfolio/positions", position),
  updatePositionName: (symbol: string, name: string) => patchJson<Position>(`/portfolio/positions/${symbol}/name`, { name }),
  addWatchItem: (item: WatchItemInput) => postJson<WatchItem>("/portfolio/watchlist", item),
  deleteWatchItem: (symbol: string) => deleteJson<WatchItem[]>(`/portfolio/watchlist/${symbol}`),
  sellPosition: (position: SellInput) => postJson<PortfolioSummary>("/portfolio/sell", position),
  marketStatus: () => getJson<MarketStatus>("/market/status"),
  marketSettings: () => getJson<MarketSettings>("/market/settings"),
  updateMarketSettings: (provider: string, tushare_token: string) => putJson<MarketSettings>("/market/settings", { provider, tushare_token }),
  marketPeriods: () => getJson<MarketPeriod[]>("/market/periods"),
  bars: (symbol: string, period: string) => getJson<PriceBar[]>(`/market/bars/${symbol}?period=${period}`),
  dashboard: (symbol: string, period: string) => getJson<DashboardData>(`/market/dashboard/${symbol}?period=${period}`),
  decision: (symbol: string) => getJson<DecisionCenter>(`/decision/${symbol}`),
  risk: (symbol: string) => getJson<RiskAdvice>(`/risk/advice/${symbol}`),
  screener: (type: "trend" | "rebound") => getJson<ScreenerResult[]>(`/screener/results?type=${type}`),
  screenerConfig: () => getJson<ScreenerConfig>("/screener/config"),
  updateScreenerConfig: (symbols: string[]) => putJson<ScreenerConfig>("/screener/config", { symbols }),
  screenerStatus: () => getJson<ScreenerStatus>("/screener/status"),
  refreshScreener: () => postJson<ScreenerStatus>("/screener/refresh", {}),
  predictionStatus: () => getJson<PredictionStatus>("/prediction/status"),
  updatePredictionSettings: (enabled: boolean, model_name: string) => putJson<PredictionStatus>("/prediction/settings", { enabled, model_name }),
  installPrediction: () => postJson<PredictionStatus>("/prediction/install", {}),
  checkPrediction: () => postJson<PredictionStatus>("/prediction/check", {}),
  prediction: (symbol: string, horizon: number) => getJson<PredictionResult>(`/prediction/${symbol}?horizon=${horizon}`),
  runBacktest: (payload: BacktestRequest) => postJson<BacktestResult>("/backtest/run", payload),
};
