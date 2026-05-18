from datetime import date, datetime, timedelta
import json
from math import sin
import os
import re
import time
from typing import Protocol
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.schemas import MarketStatus, PriceBar, StockInfo


class MarketDataProvider(Protocol):
    provider_name: str
    description: str
    last_source: str
    last_error: str | None

    def latest_price(self, symbol: str) -> float:
        ...

    def name(self, symbol: str) -> str:
        ...

    def bars(self, symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
        ...


class SampleMarketDataProvider:
    provider_name = "sample"
    description = "示例数据"
    last_source = "sample"
    last_error: str | None = None

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
    description = "AkShare/Sina 免费公开数据，失败时回退到示例数据"

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
        self._bars_cache: dict[tuple[str, str, str], tuple[datetime, list[PriceBar]]] = {}
        self.last_source = "akshare"
        self.last_error: str | None = None

    def latest_price(self, symbol: str) -> float:
        cached = self._bars_cache.get((symbol, "daily", "qfq"))
        if cached:
            return cached[1][-1].close
        bars = self.bars(symbol=symbol, period="daily")
        return bars[-1].close

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
            self.last_source = "sample"
            return self.fallback.name(symbol)
        return self._name_cache.get(symbol, self.fallback.name(symbol))

    def bars(self, symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
        cache_key = (symbol, period, adjust)
        cached = self._bars_cache.get(cache_key)
        if cached and (datetime.now() - cached[0]).total_seconds() < 60:
            self.last_source = "akshare"
            self.last_error = None
            return cached[1]

        try:
            import akshare as ak
        except Exception:
            self.last_source = "sample"
            self.last_error = "AkShare 未安装或无法导入"
            return self.fallback.bars(symbol=symbol, period=period, adjust=adjust)

        ak_period = self.period_map.get(period, "daily")
        try:
            frame = self._fetch_hist(ak, symbol=symbol, period=ak_period, adjust=adjust)
        except Exception as exc:
            try:
                bars = self._fetch_sina_bars(symbol=symbol, period=period, adjust=adjust)
                self.last_source = "sina"
                self.last_error = f"AkShare 失败，已使用 Sina 真实行情：{exc}"
                self._bars_cache[cache_key] = (datetime.now(), bars)
                return bars
            except Exception as sina_exc:
                self.last_error = f"AkShare 失败：{exc}; Sina 失败：{sina_exc}"
            if cached:
                self.last_source = "akshare"
                self.last_error = f"真实源本次刷新失败，使用最近真实缓存：{self.last_error}"
                return cached[1]
            self.last_source = "sample"
            return self.fallback.bars(symbol=symbol, period=period, adjust=adjust)

        if frame.empty:
            if cached:
                self.last_source = "akshare"
                self.last_error = "AkShare 返回空行情，使用最近真实缓存"
                return cached[1]
            self.last_source = "sample"
            self.last_error = "AkShare 返回空行情"
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
        self.last_source = "akshare"
        self.last_error = None
        self._bars_cache[cache_key] = (datetime.now(), bars)
        return bars

    def _fetch_hist(self, ak, symbol: str, period: str, adjust: str):
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return ak.stock_zh_a_hist(symbol=symbol, period=period, adjust=adjust)
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(0.8)
        raise last_error if last_error else RuntimeError("AkShare 请求失败")

    def _fetch_sina_bars(self, symbol: str, period: str, adjust: str) -> list[PriceBar]:
        if period not in {"daily", "5d", "intraday"}:
            raise RuntimeError(f"Sina K 线暂不支持周期 {period}")
        market_symbol = self._sina_symbol(symbol)
        callback = f"var _{symbol}_"
        url = (
            "https://quotes.sina.cn/cn/api/jsonp.php/"
            f"{quote(callback)}/CN_MarketDataService.getKLineData"
            f"?symbol={market_symbol}&scale=240&ma=no&datalen=180"
        )
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://finance.sina.com.cn",
            },
        )
        with urlopen(request, timeout=10) as response:
            payload = response.read().decode("utf-8", errors="ignore")
        match = re.search(r"\((\[.*\])\)", payload, re.S)
        if not match:
            raise RuntimeError("Sina 返回格式无法解析")
        rows = json.loads(match.group(1))
        if not rows:
            raise RuntimeError("Sina 返回空行情")

        bars: list[PriceBar] = []
        now = datetime.now()
        for row in rows:
            close = float(row["close"])
            volume = float(row.get("volume", 0))
            bars.append(
                PriceBar(
                    symbol=symbol,
                    period=period,
                    trade_date=row["day"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=close,
                    volume=volume,
                    amount=round(volume * close, 2),
                    turnover_rate=None,
                    adjust=adjust,
                    updated_at=now,
                )
            )
        return bars

    def _sina_symbol(self, symbol: str) -> str:
        return f"sh{symbol}" if symbol.startswith("6") else f"sz{symbol}"


sample_market_data = SampleMarketDataProvider()
akshare_market_data = AkShareMarketDataProvider(fallback=sample_market_data)
market_data: MarketDataProvider = (
    sample_market_data if os.getenv("MARKET_DATA_PROVIDER") == "sample" else akshare_market_data
)


def stock_info(symbol: str) -> StockInfo:
    return StockInfo(symbol=symbol, name=market_data.name(symbol))


def market_status() -> MarketStatus:
    if market_data.last_source == "akshare":
        description = "AkShare 真实行情"
    elif market_data.last_source == "sina":
        description = "Sina 真实行情"
    elif market_data.provider_name == "akshare":
        description = "AkShare 失败，已回退示例数据"
    else:
        description = market_data.description
    return MarketStatus(
        provider=market_data.provider_name,
        active_source=market_data.last_source,
        description=description,
        last_error=market_data.last_error,
        updated_at=datetime.now(),
    )
