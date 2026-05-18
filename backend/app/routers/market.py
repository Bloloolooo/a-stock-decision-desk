from fastapi import APIRouter

from app.schemas import MarketStatus, PriceBar, StockInfo
from app.services.market_data import market_data, market_status, stock_info

router = APIRouter()


@router.get("/status", response_model=MarketStatus)
def get_market_status() -> MarketStatus:
    return market_status()


@router.get("/stocks/{symbol}", response_model=StockInfo)
def get_stock_info(symbol: str) -> StockInfo:
    return stock_info(symbol)


@router.get("/bars/{symbol}", response_model=list[PriceBar])
def get_bars(symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
    return market_data.bars(symbol=symbol, period=period, adjust=adjust)
