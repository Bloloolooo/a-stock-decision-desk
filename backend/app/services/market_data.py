from datetime import date, datetime, timedelta
from math import sin
import os
from typing import Protocol

from app.schemas import MarketStatus, PriceBar, StockInfo


class MarketDataProvider(Protocol):
    provider_name: str
    description: str

    def latest_price(self, symbol: str) -> float:
        ...

    def name(self, symbol: str) -> str:
        ...

    def bars(self, symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
        ...


class SampleMarketDataProvider:
    provider_name = "sample"
    description = "示例数据"

    names = {
        "300308": "中际旭创",
        "300750": "宁德时代",
        "600519": "贵州茅台",
        "300502": "新易盛",
        "601138": "工业富联",
    }

    base_prices = {
        "300308": 165.42,
        "300750": 198.31,
        "600519": 1578.2,
        "300502": 118.74,
        "601138": 26.85,
    }

    def latest_price(self, symbol: str) -> float:
        return self.base_prices.get(symbol, 32.8)

    def name(self, symbol: str) -> str:
        return self.names.get(symbol, f"股票 {symbol}")

    def bars(self, symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
        today = date.today()
        base = self.latest_price(symbol)
        bars: list[PriceBar] = []
        for index in range(90):
            days_ago = 89 - index
            trade_date = today - timedelta(days=days_ago)
            trend = (index - 45) * base * 0.0028
            wave = sin(index / 4) * base * 0.025
            close = max(base * 0.55, base + trend + wave)
            open_price = close * (1 + sin(index / 3) * 0.012)
            high = max(open_price, close) * 1.018
            low = min(open_price, close) * 0.982
            volume = 1_200_000 + index * 18_000 + abs(sin(index)) * 550_000
            bars.append(
                PriceBar(
                    symbol=symbol,
                    period=period,
                    trade_date=trade_date,
                    open=round(open_price, 2),
                    high=round(high, 2),
                    low=round(low, 2),
                    close=round(close, 2),
                    volume=round(volume, 2),
                    amount=round(volume * close, 2),
                    turnover_rate=round(2.4 + sin(index / 5), 2),
                    adjust=adjust,
                    updated_at=datetime.now(),
                )
            )
        return bars


class AkShareMarketDataProvider:
    provider_name = "akshare"
    description = "AkShare 免费公开数据，失败时回退到示例数据"

    period_map = {
        "daily": "daily",
        "weekly": "weekly",
        "monthly": "monthly",
        "5d": "daily",
        "intraday": "daily",
    }

    def __init__(self, fallback: MarketDataProvider | None = None) -> None:
        self.fallback = fallback or SampleMarketDataProvider()
        self._name_cache: dict[str, str] = {}

    def latest_price(self, symbol: str) -> float:
        try:
            bars = self.bars(symbol=symbol, period="daily")
            return bars[-1].close
        except Exception:
            return self.fallback.latest_price(symbol)

    def name(self, symbol: str) -> str:
        if symbol in self._name_cache:
            return self._name_cache[symbol]
        try:
            import akshare as ak

            frame = ak.stock_info_a_code_name()
            for row in frame.to_dict("records"):
                code = str(row.get("code") or row.get("代码") or "")
                name = str(row.get("name") or row.get("名称") or "")
                if code and name:
                    self._name_cache[code] = name
        except Exception:
            return self.fallback.name(symbol)
        return self._name_cache.get(symbol, self.fallback.name(symbol))

    def bars(self, symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
        try:
            import akshare as ak
        except Exception:
            return self.fallback.bars(symbol=symbol, period=period, adjust=adjust)

        ak_period = self.period_map.get(period, "daily")
        try:
            frame = ak.stock_zh_a_hist(symbol=symbol, period=ak_period, adjust=adjust)
        except Exception:
            return self.fallback.bars(symbol=symbol, period=period, adjust=adjust)

        if frame.empty:
            return self.fallback.bars(symbol=symbol, period=period, adjust=adjust)

        frame = frame.tail(180)
        bars: list[PriceBar] = []
        now = datetime.now()
        for row in frame.to_dict("records"):
            bars.append(
                PriceBar(
                    symbol=symbol,
                    period=period,
                    trade_date=row["日期"],
                    open=float(row["开盘"]),
                    high=float(row["最高"]),
                    low=float(row["最低"]),
                    close=float(row["收盘"]),
                    volume=float(row.get("成交量", 0)),
                    amount=float(row.get("成交额", 0)),
                    turnover_rate=float(row["换手率"]) if row.get("换手率") not in (None, "") else None,
                    adjust=adjust,
                    updated_at=now,
                )
            )
        return bars


sample_market_data = SampleMarketDataProvider()
akshare_market_data = AkShareMarketDataProvider(fallback=sample_market_data)
market_data: MarketDataProvider = (
    akshare_market_data if os.getenv("MARKET_DATA_PROVIDER") == "akshare" else sample_market_data
)


def stock_info(symbol: str) -> StockInfo:
    return StockInfo(symbol=symbol, name=market_data.name(symbol))


def market_status() -> MarketStatus:
    return MarketStatus(
        provider=market_data.provider_name,
        description=market_data.description,
        updated_at=datetime.now(),
    )
