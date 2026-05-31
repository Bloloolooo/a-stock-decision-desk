from datetime import date, datetime, timedelta
import json
from math import sin
import os
import re
import time
from typing import Protocol
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.db import get_connection, init_db
from app.schemas import MarketPeriod, MarketSettings, MarketStatus, PriceBar, StockInfo

CACHE_TTL_SECONDS = 300


def _akshare_enabled() -> bool:
    value = os.getenv("ENABLE_AKSHARE", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _price(value: object) -> float:
    return round(float(value), 2)


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

    def stocks(self) -> list[StockInfo]:
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
        return self.names.get(symbol, "")

    def stocks(self) -> list[StockInfo]:
        return [StockInfo(symbol=symbol, name=name) for symbol, name in self.names.items()]

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
                    timestamp=trade_date.isoformat(),
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
    description = "AkShare 免费公开数据，默认需显式启用"

    period_map = {
        "daily": "daily",
        "weekly": "weekly",
        "monthly": "monthly",
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
        if not _akshare_enabled():
            return self._safe_name(symbol)
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
        if symbol not in self._name_cache:
            sina_name = self._fetch_sina_name(symbol)
            if sina_name:
                self._name_cache[symbol] = sina_name
        return self._name_cache.get(symbol, self.fallback.name(symbol))

    def stocks(self) -> list[StockInfo]:
        if not _akshare_enabled():
            self.last_source = "sample"
            self.last_error = "AkShare 默认关闭，股票列表暂用本地示例池"
            return self.fallback.stocks()
        try:
            import akshare as ak

            frame = ak.stock_info_a_code_name()
            stocks: list[StockInfo] = []
            for row in frame.to_dict("records"):
                code = str(row.get("code") or row.get("代码") or "").strip()
                name = str(row.get("name") or row.get("名称") or "").strip()
                if len(code) == 6 and code.isdigit() and name:
                    self._name_cache[code] = name
                    stocks.append(StockInfo(symbol=code, name=name))
            if stocks:
                self.last_source = "akshare"
                self.last_error = None
                return stocks
        except Exception as exc:
            self.last_source = "sample"
            self.last_error = f"AkShare 股票列表失败：{exc}"
        return self.fallback.stocks()

    def _safe_name(self, symbol: str) -> str:
        if symbol in self._name_cache:
            return self._name_cache[symbol]
        sina_name = self._fetch_sina_name(symbol)
        if sina_name:
            self._name_cache[symbol] = sina_name
            self.last_source = "sina"
            return sina_name
        return self.fallback.name(symbol)

    def _fetch_sina_name(self, symbol: str) -> str:
        market_symbol = self._sina_symbol(symbol)
        url = f"https://hq.sinajs.cn/list={market_symbol}"
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://finance.sina.com.cn",
            },
        )
        try:
            with urlopen(request, timeout=5) as response:
                payload = response.read().decode("gbk", errors="ignore")
        except Exception:
            return ""
        match = re.search(r'="([^,"]+),', payload)
        if not match:
            return ""
        name = match.group(1).strip()
        return "" if not name or name == market_symbol else name

    def bars(self, symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
        cache_key = (symbol, period, adjust)
        cached = self._bars_cache.get(cache_key)
        if cached and (datetime.now() - cached[0]).total_seconds() < CACHE_TTL_SECONDS:
            self.last_source = "akshare"
            self.last_error = None
            return cached[1]

        if not _akshare_enabled():
            self.last_error = "AkShare 默认关闭，已使用 Sina/示例备用源；如确需 AkShare，请设置 ENABLE_AKSHARE=1"
            return self._fetch_sina_or_sample(symbol=symbol, period=period, adjust=adjust)

        try:
            import akshare as ak
        except Exception:
            self.last_source = "sample"
            self.last_error = "AkShare 未安装或无法导入"
            return self.fallback.bars(symbol=symbol, period=period, adjust=adjust)

        try:
            if period in {"intraday", "5d"}:
                bars = self._fetch_minute_bars(ak, symbol=symbol, period=period)
                self.last_source = "akshare"
                self.last_error = None
                self._bars_cache[cache_key] = (datetime.now(), bars)
                return bars
            ak_period = self.period_map.get(period, "daily")
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
                    timestamp=str(row["日期"]),
                    open=_price(row["开盘"]),
                    high=_price(row["最高"]),
                    low=_price(row["最低"]),
                    close=_price(row["收盘"]),
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

    def _fetch_minute_bars(self, ak, symbol: str, period: str) -> list[PriceBar]:
        frame = ak.stock_zh_a_minute(symbol=self._sina_symbol(symbol), period="1", adjust="")
        if frame.empty:
            raise RuntimeError("AkShare 分钟行情返回空数据")
        frame = frame.tail(1200 if period == "5d" else 300)
        bars: list[PriceBar] = []
        now = datetime.now()
        for row in frame.to_dict("records"):
            timestamp = str(row["day"])
            close = float(row["close"])
            volume = float(row.get("volume", 0))
            bars.append(
                PriceBar(
                    symbol=symbol,
                    period=period,
                    trade_date=timestamp.split(" ")[0],
                    timestamp=timestamp,
                    open=_price(row["open"]),
                    high=_price(row["high"]),
                    low=_price(row["low"]),
                    close=_price(close),
                    volume=volume,
                    amount=float(row.get("amount", volume * close)),
                    turnover_rate=None,
                    adjust="",
                    updated_at=now,
                )
            )
        return bars

    def _fetch_sina_bars(self, symbol: str, period: str, adjust: str) -> list[PriceBar]:
        if period not in {"daily", "weekly", "monthly", "5d", "intraday"}:
            raise RuntimeError(f"Sina K 线暂不支持周期 {period}")
        if period in {"weekly", "monthly"}:
            return self._aggregate_sina_daily(symbol=symbol, period=period, adjust=adjust)

        market_symbol = self._sina_symbol(symbol)
        callback = f"var _{symbol}_"
        scale = 1 if period in {"intraday", "5d"} else 240
        datalen = 1200 if period == "5d" else 300 if period == "intraday" else 180
        url = (
            "https://quotes.sina.cn/cn/api/jsonp.php/"
            f"{quote(callback)}/CN_MarketDataService.getKLineData"
            f"?symbol={market_symbol}&scale={scale}&ma=no&datalen={datalen}"
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
            timestamp = row["day"]
            close = float(row["close"])
            volume = float(row.get("volume", 0))
            bars.append(
                PriceBar(
                    symbol=symbol,
                    period=period,
                    trade_date=timestamp.split(" ")[0],
                    timestamp=timestamp,
                    open=_price(row["open"]),
                    high=_price(row["high"]),
                    low=_price(row["low"]),
                    close=_price(close),
                    volume=volume,
                    amount=round(volume * close, 2),
                    turnover_rate=None,
                    adjust=adjust,
                    updated_at=now,
                )
            )
        return bars

    def _aggregate_sina_daily(self, symbol: str, period: str, adjust: str) -> list[PriceBar]:
        daily_bars = self._fetch_sina_bars(symbol=symbol, period="daily", adjust=adjust)
        grouped: dict[str, list[PriceBar]] = {}
        for bar in daily_bars:
            day = date.fromisoformat(bar.trade_date.isoformat())
            if period == "weekly":
                year, week, _ = day.isocalendar()
                key = f"{year}-W{week:02d}"
            else:
                key = day.strftime("%Y-%m")
            grouped.setdefault(key, []).append(bar)

        bars: list[PriceBar] = []
        now = datetime.now()
        for group in grouped.values():
            first = group[0]
            last = group[-1]
            volume = sum(bar.volume for bar in group)
            amount = sum(bar.amount for bar in group)
            bars.append(
                PriceBar(
                    symbol=symbol,
                    period=period,
                    trade_date=last.trade_date,
                    timestamp=last.trade_date.isoformat(),
                    open=_price(first.open),
                    high=_price(max(bar.high for bar in group)),
                    low=_price(min(bar.low for bar in group)),
                    close=_price(last.close),
                    volume=round(volume, 2),
                    amount=round(amount, 2),
                    turnover_rate=None,
                    adjust=adjust,
                    updated_at=now,
                )
            )
        return bars[-180:]

    def _fetch_sina_or_sample(self, symbol: str, period: str, adjust: str) -> list[PriceBar]:
        previous_error = self.last_error
        try:
            bars = self._fetch_sina_bars(symbol=symbol, period=period, adjust=adjust)
            self.last_source = "sina"
            if previous_error:
                self.last_error = f"{previous_error}；已使用 Sina 真实行情"
            else:
                self.last_error = None
            self._bars_cache[(symbol, period, adjust)] = (datetime.now(), bars)
            return bars
        except Exception as exc:
            self.last_source = "sample"
            prefix = f"{previous_error}；" if previous_error else ""
            self.last_error = f"{prefix}Sina 失败：{exc}；已回退示例数据"
            return self.fallback.bars(symbol=symbol, period=period, adjust=adjust)

    def _sina_symbol(self, symbol: str) -> str:
        return f"sh{symbol}" if symbol.startswith("6") else f"sz{symbol}"


class SinaMarketDataProvider(AkShareMarketDataProvider):
    provider_name = "sina"
    description = "Sina 免费公开行情"

    def name(self, symbol: str) -> str:
        return self._safe_name(symbol)

    def stocks(self) -> list[StockInfo]:
        self.last_source = "sample"
        self.last_error = "Sina 暂无全市场股票列表接口，已使用本地示例池"
        return self.fallback.stocks()

    def bars(self, symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
        cache_key = (symbol, period, adjust)
        cached = self._bars_cache.get(cache_key)
        if cached and (datetime.now() - cached[0]).total_seconds() < CACHE_TTL_SECONDS:
            self.last_source = "sina"
            self.last_error = None
            return cached[1]
        try:
            bars = self._fetch_sina_bars(symbol=symbol, period=period, adjust=adjust)
            self.last_source = "sina"
            self.last_error = None
            self._bars_cache[cache_key] = (datetime.now(), bars)
            return bars
        except Exception as exc:
            self.last_source = "sample"
            self.last_error = f"Sina 失败：{exc}"
            return self.fallback.bars(symbol=symbol, period=period, adjust=adjust)


class TushareMarketDataProvider(AkShareMarketDataProvider):
    provider_name = "tushare"
    description = "Tushare Pro，可选 Token 数据源"

    def __init__(self, token: str, fallback: MarketDataProvider | None = None) -> None:
        super().__init__(fallback=fallback)
        self.token = token

    def bars(self, symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
        if not self.token:
            self.last_source = "sample"
            self.last_error = "Tushare Token 未配置"
            return self.fallback.bars(symbol=symbol, period=period, adjust=adjust)
        if period not in {"daily", "weekly", "monthly"}:
            self.last_error = "Tushare 分时接口暂未接入，已回退 Sina/示例数据"
            return self._fetch_sina_or_sample(symbol=symbol, period=period, adjust=adjust)
        cache_key = (symbol, period, adjust)
        cached = self._bars_cache.get(cache_key)
        if cached and (datetime.now() - cached[0]).total_seconds() < CACHE_TTL_SECONDS:
            self.last_source = "tushare"
            self.last_error = None
            return cached[1]
        try:
            import tushare as ts

            ts.set_token(self.token)
            pro = ts.pro_api()
            ts_code = f"{symbol}.SH" if symbol.startswith("6") else f"{symbol}.SZ"
            frame = pro.daily(ts_code=ts_code)
            if frame.empty:
                raise RuntimeError("Tushare 返回空行情")
            frame = frame.sort_values("trade_date").tail(180)
            bars: list[PriceBar] = []
            now = datetime.now()
            for row in frame.to_dict("records"):
                trade_date = datetime.strptime(str(row["trade_date"]), "%Y%m%d").date()
                close = float(row["close"])
                volume = float(row.get("vol", 0)) * 100
                bars.append(
                    PriceBar(
                        symbol=symbol,
                        period=period,
                        trade_date=trade_date,
                        timestamp=trade_date.isoformat(),
                        open=_price(row["open"]),
                        high=_price(row["high"]),
                        low=_price(row["low"]),
                        close=_price(close),
                        volume=volume,
                        amount=float(row.get("amount", 0)) * 1000,
                        turnover_rate=None,
                        adjust=adjust,
                        updated_at=now,
                    )
                )
            if period in {"weekly", "monthly"}:
                bars = self._aggregate_bars(bars=bars, period=period, adjust=adjust)
            self.last_source = "tushare"
            self.last_error = None
            self._bars_cache[cache_key] = (datetime.now(), bars)
            return bars
        except Exception as exc:
            error = f"Tushare 失败：{exc}"
            self.last_error = error
            bars = self._fetch_sina_or_sample(symbol=symbol, period=period, adjust=adjust)
            self.last_error = f"{error}；已使用 {self.last_source} 备用源"
            return bars

    def _aggregate_bars(self, bars: list[PriceBar], period: str, adjust: str) -> list[PriceBar]:
        grouped: dict[str, list[PriceBar]] = {}
        for bar in bars:
            day = bar.trade_date
            if period == "weekly":
                year, week, _ = day.isocalendar()
                key = f"{year}-W{week:02d}"
            else:
                key = day.strftime("%Y-%m")
            grouped.setdefault(key, []).append(bar)
        now = datetime.now()
        result: list[PriceBar] = []
        for group in grouped.values():
            first = group[0]
            last = group[-1]
            result.append(
                PriceBar(
                    symbol=last.symbol,
                    period=period,
                    trade_date=last.trade_date,
                    timestamp=last.trade_date.isoformat(),
                    open=_price(first.open),
                    high=_price(max(bar.high for bar in group)),
                    low=_price(min(bar.low for bar in group)),
                    close=_price(last.close),
                    volume=sum(bar.volume for bar in group),
                    amount=sum(bar.amount for bar in group),
                    turnover_rate=None,
                    adjust=adjust,
                    updated_at=now,
                )
            )
        return result


class EfinanceMarketDataProvider(AkShareMarketDataProvider):
    provider_name = "efinance"
    description = "efinance 免费公开行情"

    period_map = {
        "daily": 101,
        "weekly": 102,
        "monthly": 103,
    }

    def bars(self, symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
        if period not in self.period_map:
            self.last_error = "efinance 分时接口暂未接入，已回退 Sina/示例数据"
            return self._fetch_sina_or_sample(symbol=symbol, period=period, adjust=adjust)
        cache_key = (symbol, period, adjust)
        cached = self._bars_cache.get(cache_key)
        if cached and (datetime.now() - cached[0]).total_seconds() < CACHE_TTL_SECONDS:
            self.last_source = "efinance"
            self.last_error = None
            return cached[1]
        try:
            import efinance as ef

            frame = ef.stock.get_quote_history(stock_code=symbol, klt=self.period_map[period], fqt=1 if adjust == "qfq" else 0)
            if frame.empty:
                raise RuntimeError("efinance 返回空行情")
            frame = frame.tail(180)
            now = datetime.now()
            bars: list[PriceBar] = []
            for row in frame.to_dict("records"):
                trade_date = datetime.strptime(str(row["日期"])[:10], "%Y-%m-%d").date()
                bars.append(
                    PriceBar(
                        symbol=symbol,
                        period=period,
                        trade_date=trade_date,
                        timestamp=trade_date.isoformat(),
                        open=_price(row["开盘"]),
                        high=_price(row["最高"]),
                        low=_price(row["最低"]),
                        close=_price(row["收盘"]),
                        volume=float(row.get("成交量", 0)),
                        amount=float(row.get("成交额", 0)),
                        turnover_rate=float(row["换手率"]) if row.get("换手率") not in (None, "") else None,
                        adjust=adjust,
                        updated_at=now,
                    )
                )
            self.last_source = "efinance"
            self.last_error = None
            self._bars_cache[cache_key] = (datetime.now(), bars)
            return bars
        except Exception as exc:
            error = f"efinance 失败：{exc}"
            self.last_error = error
            bars = self._fetch_sina_or_sample(symbol=symbol, period=period, adjust=adjust)
            self.last_error = f"{error}；已使用 {self.last_source} 备用源"
            return bars


class BaoStockMarketDataProvider(AkShareMarketDataProvider):
    provider_name = "baostock"
    description = "BaoStock 免费 A 股历史行情"

    period_map = {
        "daily": "d",
        "weekly": "w",
        "monthly": "m",
    }

    def bars(self, symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
        if period not in self.period_map:
            self.last_error = "BaoStock 分时接口暂未接入，已回退 Sina/示例数据"
            return self._fetch_sina_or_sample(symbol=symbol, period=period, adjust=adjust)
        cache_key = (symbol, period, adjust)
        cached = self._bars_cache.get(cache_key)
        if cached and (datetime.now() - cached[0]).total_seconds() < CACHE_TTL_SECONDS:
            self.last_source = "baostock"
            self.last_error = None
            return cached[1]
        try:
            import baostock as bs

            login = bs.login()
            if login.error_code != "0":
                raise RuntimeError(login.error_msg)
            try:
                code = f"sh.{symbol}" if symbol.startswith("6") else f"sz.{symbol}"
                start_date = (date.today() - timedelta(days=420)).isoformat()
                result = bs.query_history_k_data_plus(
                    code,
                    "date,code,open,high,low,close,volume,amount,turn",
                    start_date=start_date,
                    end_date=date.today().isoformat(),
                    frequency=self.period_map[period],
                    adjustflag="2" if adjust == "qfq" else "3" if adjust == "hfq" else "1",
                )
                rows = []
                while result.error_code == "0" and result.next():
                    rows.append(result.get_row_data())
                if result.error_code != "0":
                    raise RuntimeError(result.error_msg)
            finally:
                bs.logout()
            if not rows:
                raise RuntimeError("BaoStock 返回空行情")
            now = datetime.now()
            bars: list[PriceBar] = []
            for row in rows[-180:]:
                trade_date = datetime.strptime(row[0], "%Y-%m-%d").date()
                close = float(row[5])
                volume = float(row[6] or 0)
                bars.append(
                    PriceBar(
                        symbol=symbol,
                        period=period,
                        trade_date=trade_date,
                        timestamp=trade_date.isoformat(),
                        open=_price(row[2]),
                        high=_price(row[3]),
                        low=_price(row[4]),
                        close=_price(close),
                        volume=volume,
                        amount=float(row[7] or 0),
                        turnover_rate=float(row[8]) if row[8] not in (None, "") else None,
                        adjust=adjust,
                        updated_at=now,
                    )
                )
            self.last_source = "baostock"
            self.last_error = None
            self._bars_cache[cache_key] = (datetime.now(), bars)
            return bars
        except Exception as exc:
            error = f"BaoStock 失败：{exc}"
            self.last_error = error
            bars = self._fetch_sina_or_sample(symbol=symbol, period=period, adjust=adjust)
            self.last_error = f"{error}；已使用 {self.last_source} 备用源"
            return bars


class TencentMarketDataProvider(AkShareMarketDataProvider):
    provider_name = "tencent"
    description = "Tencent Finance 公开 HTTP 行情"

    period_map = {
        "daily": "day",
        "weekly": "week",
        "monthly": "month",
    }

    def bars(self, symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
        if period not in self.period_map:
            self.last_error = "Tencent 分时接口暂未接入，已回退 Sina"
            return self._fetch_sina_or_sample(symbol=symbol, period=period, adjust=adjust)
        cache_key = (symbol, period, adjust)
        cached = self._bars_cache.get(cache_key)
        if cached and (datetime.now() - cached[0]).total_seconds() < CACHE_TTL_SECONDS:
            self.last_source = "tencent"
            self.last_error = None
            return cached[1]
        try:
            market_symbol = self._sina_symbol(symbol)
            period_key = self.period_map[period]
            adjust_key = "qfq" if adjust == "qfq" else "hfq" if adjust == "hfq" else ""
            url = (
                "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
                f"?param={market_symbol},{period_key},,,180,{adjust_key}"
            )
            request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"})
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
            data = payload.get("data", {}).get(market_symbol, {})
            rows = data.get(f"{adjust_key}{period_key}") or data.get(period_key) or data.get("qfqday") or data.get("day") or []
            if not rows:
                raise RuntimeError("Tencent 返回空行情")
            now = datetime.now()
            bars: list[PriceBar] = []
            for row in rows[-180:]:
                trade_date = datetime.strptime(str(row[0])[:10], "%Y-%m-%d").date()
                close = float(row[2])
                volume = float(row[5]) if len(row) > 5 else 0.0
                bars.append(
                    PriceBar(
                        symbol=symbol,
                        period=period,
                        trade_date=trade_date,
                        timestamp=trade_date.isoformat(),
                        open=_price(row[1]),
                        high=_price(row[3]),
                        low=_price(row[4]),
                        close=_price(close),
                        volume=volume,
                        amount=round(volume * close, 2),
                        turnover_rate=None,
                        adjust=adjust,
                        updated_at=now,
                    )
                )
            self.last_source = "tencent"
            self.last_error = None
            self._bars_cache[cache_key] = (datetime.now(), bars)
            return bars
        except Exception as exc:
            self.last_error = f"Tencent 失败：{exc}"
            return self._fetch_sina_or_sample(symbol=symbol, period=period, adjust=adjust)

class MarketDataManager:
    provider_name = "auto"
    description = "自动选择真实行情源"
    last_source = "auto"
    last_error: str | None = None

    def __init__(self) -> None:
        init_db()
        self.sample = SampleMarketDataProvider()
        self.akshare = AkShareMarketDataProvider(fallback=self.sample)
        self.sina = SinaMarketDataProvider(fallback=self.sample)
        self.efinance = EfinanceMarketDataProvider(fallback=self.sample)
        self.baostock = BaoStockMarketDataProvider(fallback=self.sample)
        self.tencent = TencentMarketDataProvider(fallback=self.sample)
        self._tushare_token = ""
        self.tushare = TushareMarketDataProvider(token="", fallback=self.sample)

    def settings(self) -> MarketSettings:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT provider, tushare_token, updated_at
                FROM market_settings WHERE id = 1
                """
            ).fetchone()
        if not row:
            return MarketSettings(provider="auto", tushare_token_configured=False, updated_at=datetime.now())
        token = row["tushare_token"] or ""
        return MarketSettings(
            provider=row["provider"] or "auto",
            tushare_token_configured=bool(token.strip()),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def update_settings(self, provider: str, tushare_token: str = "") -> MarketSettings:
        normalized = provider if provider in {"auto", "akshare", "sina", "tushare", "efinance", "baostock", "tencent", "sample"} else "auto"
        current_token = self._stored_tushare_token()
        token = tushare_token.strip() or current_token
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE market_settings
                SET provider = ?, tushare_token = ?, updated_at = datetime('now')
                WHERE id = 1
                """,
                (normalized, token),
            )
        self._tushare_token = token
        self.tushare = TushareMarketDataProvider(token=token, fallback=self.sample)
        self._sync_status(self._provider())
        return self.settings()

    def latest_price(self, symbol: str) -> float:
        return self._call("latest_price", symbol)

    def name(self, symbol: str) -> str:
        normalized = symbol.strip()
        provider = self._provider()
        candidates: list[MarketDataProvider] = [provider]
        fallbacks: list[MarketDataProvider] = [self.sina, self.tencent, self.efinance, self.baostock, self.sample]
        if _akshare_enabled():
            fallbacks.insert(0, self.akshare)
        for fallback in fallbacks:
            if fallback not in candidates:
                candidates.append(fallback)
        for candidate in candidates:
            try:
                name = candidate.name(normalized).strip()
            except Exception:
                continue
            if name and not name.startswith("股票"):
                self._sync_status(candidate)
                return name
        self._sync_status(provider)
        return f"股票 {normalized}"

    def bars(self, symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
        return self._call("bars", symbol, period, adjust)

    def stocks(self) -> list[StockInfo]:
        configured = self._provider()
        candidates: list[MarketDataProvider] = [configured]
        fallbacks: list[MarketDataProvider] = [self.efinance, self.sina, self.tencent, self.baostock, self.sample]
        if _akshare_enabled():
            fallbacks.insert(0, self.akshare)
        for fallback in fallbacks:
            if fallback not in candidates:
                candidates.append(fallback)
        for candidate in candidates:
            try:
                stocks = candidate.stocks()
            except Exception:
                continue
            if stocks:
                self._sync_status(candidate)
                return stocks
        return self.sample.stocks()

    def _call(self, method: str, *args):
        provider = self._provider()
        result = getattr(provider, method)(*args)
        self._sync_status(provider)
        return result

    def _provider(self) -> MarketDataProvider:
        configured = self.settings().provider
        self.provider_name = configured
        if configured == "sample":
            return self.sample
        if configured == "sina":
            return self.sina
        if configured == "efinance":
            return self.efinance
        if configured == "baostock":
            return self.baostock
        if configured == "tencent":
            return self.tencent
        if configured == "tushare":
            token = self._stored_tushare_token()
            if token != self._tushare_token:
                self._tushare_token = token
                self.tushare = TushareMarketDataProvider(token=token, fallback=self.sample)
            return self.tushare
        if configured == "akshare":
            if _akshare_enabled():
                return self.akshare
            self.tencent.last_source = "tencent"
            self.tencent.last_error = "AkShare 默认关闭，已改用 Tencent/Sina 安全数据源；如确需 AkShare，请设置 ENABLE_AKSHARE=1"
            return self.tencent
        return self.tencent

    def _stored_tushare_token(self) -> str:
        with get_connection() as connection:
            row = connection.execute("SELECT tushare_token FROM market_settings WHERE id = 1").fetchone()
        return (row["tushare_token"] or "") if row else ""

    def _sync_status(self, provider: MarketDataProvider) -> None:
        self.last_source = provider.last_source
        self.last_error = provider.last_error
        self.description = provider.description


sample_market_data = SampleMarketDataProvider()
akshare_market_data = AkShareMarketDataProvider(fallback=sample_market_data)
market_data = MarketDataManager()
if os.getenv("MARKET_DATA_PROVIDER") == "sample":
    market_data.update_settings("sample")


def stock_info(symbol: str) -> StockInfo:
    return StockInfo(symbol=symbol, name=market_data.name(symbol))


def stock_universe() -> list[StockInfo]:
    return market_data.stocks()


def market_status() -> MarketStatus:
    settings = market_data.settings()
    if market_data.last_source == "akshare":
        description = "AkShare 真实行情"
    elif market_data.last_source == "sina":
        description = "Sina 真实行情"
    elif market_data.last_source == "tushare":
        description = "Tushare 真实行情"
    elif market_data.last_source == "efinance":
        description = "efinance 真实行情"
    elif market_data.last_source == "baostock":
        description = "BaoStock 真实行情"
    elif market_data.last_source == "tencent":
        description = "Tencent 真实行情"
    elif settings.provider == "auto":
        description = "自动数据源失败，已回退示例数据"
    elif settings.provider == "akshare":
        description = "AkShare 未启用或失败，已回退备用源"
    elif settings.provider == "tushare":
        description = "Tushare 失败，已回退备用源"
    elif settings.provider == "efinance":
        description = "efinance 失败，已回退备用源"
    elif settings.provider == "baostock":
        description = "BaoStock 失败，已回退备用源"
    elif settings.provider == "tencent":
        description = "Tencent 失败，已回退备用源"
    else:
        description = market_data.description
    return MarketStatus(
        provider=settings.provider,
        active_source=market_data.last_source,
        description=description,
        last_error=market_data.last_error,
        updated_at=datetime.now(),
    )


def market_settings() -> MarketSettings:
    return market_data.settings()


def update_market_settings(provider: str, tushare_token: str = "") -> MarketSettings:
    return market_data.update_settings(provider=provider, tushare_token=tushare_token)


def market_periods() -> list[MarketPeriod]:
    return [
        MarketPeriod(key="intraday", label="分时", description="1 分钟线"),
        MarketPeriod(key="5d", label="5日", description="近 5 日 1 分钟线"),
        MarketPeriod(key="daily", label="日K", description="日线"),
        MarketPeriod(key="weekly", label="周K", description="周线"),
        MarketPeriod(key="monthly", label="月K", description="月线"),
    ]
