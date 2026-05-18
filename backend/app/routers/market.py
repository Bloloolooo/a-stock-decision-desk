from fastapi import APIRouter

from app.schemas import PriceBar
from app.services.market_data import market_data

router = APIRouter()


@router.get("/bars/{symbol}", response_model=list[PriceBar])
def get_bars(symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
    return market_data.bars(symbol=symbol, period=period, adjust=adjust)
