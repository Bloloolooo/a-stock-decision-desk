from datetime import date, datetime, timedelta
from math import sin

from app.schemas import PriceBar


class SampleMarketData:
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


sample_market_data = SampleMarketData()
