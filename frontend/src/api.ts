import type { MarketPeriod, MarketStatus, PortfolioSummary, Position, PositionInput, PriceBar, RiskAdvice, ScreenerConfig, ScreenerResult, ScreenerStatus, SellInput, TradeRecord } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
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
    throw new Error(`API request failed: ${response.status}`);
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
    throw new Error(`API request failed: ${response.status}`);
  }
  return response.json();
}

export const api = {
  summary: () => getJson<PortfolioSummary>("/portfolio/summary"),
  positions: () => getJson<Position[]>("/portfolio/positions"),
  trades: () => getJson<TradeRecord[]>("/portfolio/trades"),
  updateCash: (cash: number) => postJson<PortfolioSummary>("/portfolio/cash", { cash }),
  upsertPosition: (position: PositionInput) => postJson<Position>("/portfolio/positions", position),
  sellPosition: (position: SellInput) => postJson<PortfolioSummary>("/portfolio/sell", position),
  marketStatus: () => getJson<MarketStatus>("/market/status"),
  marketPeriods: () => getJson<MarketPeriod[]>("/market/periods"),
  bars: (symbol: string, period: string) => getJson<PriceBar[]>(`/market/bars/${symbol}?period=${period}`),
  risk: (symbol: string) => getJson<RiskAdvice>(`/risk/advice/${symbol}`),
  screener: (type: "trend" | "rebound") => getJson<ScreenerResult[]>(`/screener/results?type=${type}`),
  screenerConfig: () => getJson<ScreenerConfig>("/screener/config"),
  updateScreenerConfig: (symbols: string[]) => putJson<ScreenerConfig>("/screener/config", { symbols }),
  screenerStatus: () => getJson<ScreenerStatus>("/screener/status"),
  refreshScreener: () => postJson<ScreenerStatus>("/screener/refresh", {}),
};
