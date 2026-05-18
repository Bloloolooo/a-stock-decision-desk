import type { PortfolioSummary, Position, PriceBar, RiskAdvice, ScreenerResult } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return response.json();
}

export const api = {
  summary: () => getJson<PortfolioSummary>("/portfolio/summary"),
  positions: () => getJson<Position[]>("/portfolio/positions"),
  bars: (symbol: string, period: string) => getJson<PriceBar[]>(`/market/bars/${symbol}?period=${period}`),
  risk: (symbol: string) => getJson<RiskAdvice>(`/risk/advice/${symbol}`),
  screener: (type: "trend" | "rebound") => getJson<ScreenerResult[]>(`/screener/results?type=${type}`),
};
