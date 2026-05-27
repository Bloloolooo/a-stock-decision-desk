from fastapi import APIRouter

from datetime import datetime

from app.schemas import DashboardData, MarketPeriod, MarketSettings, MarketSettingsUpdate, MarketStatus, PriceBar, StockInfo
from app.services.decision import decision_service
from app.services.market_data import market_data, market_periods, market_settings, market_status, stock_info, update_market_settings
from app.services.risk import risk_service

router = APIRouter()


@router.get("/status", response_model=MarketStatus)
def get_market_status() -> MarketStatus:
    return market_status()


@router.get("/settings", response_model=MarketSettings)
def get_market_settings() -> MarketSettings:
    return market_settings()


@router.put("/settings", response_model=MarketSettings)
def save_market_settings(payload: MarketSettingsUpdate) -> MarketSettings:
    return update_market_settings(provider=payload.provider, tushare_token=payload.tushare_token)


@router.get("/periods", response_model=list[MarketPeriod])
def get_market_periods() -> list[MarketPeriod]:
    return market_periods()


@router.get("/stocks/{symbol}", response_model=StockInfo)
def get_stock_info(symbol: str) -> StockInfo:
    return stock_info(symbol)


@router.get("/bars/{symbol}", response_model=list[PriceBar])
def get_bars(symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
    return market_data.bars(symbol=symbol, period=period, adjust=adjust)


@router.get("/dashboard/{symbol}", response_model=DashboardData)
def get_dashboard(symbol: str, period: str = "daily", adjust: str = "qfq") -> DashboardData:
    bars = market_data.bars(symbol=symbol, period=period, adjust=adjust)
    return DashboardData(
        symbol=symbol,
        period=period,
        bars=bars,
        risk=risk_service.advice(symbol),
        decision=decision_service.decision(symbol=symbol),
        market_status=market_status(),
        updated_at=datetime.now(),
    )
