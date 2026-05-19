from dataclasses import dataclass
from datetime import datetime
import os

from app.schemas import PriceBar, ScreenerResult
from app.services.market_data import market_data


DEFAULT_POOL = [
    "300308",
    "300502",
    "601138",
    "300750",
    "600519",
    "002594",
    "000858",
    "600036",
    "601318",
    "600276",
    "002415",
    "000063",
    "603259",
    "600795",
    "600312",
    "603871",
]


@dataclass
class StockSignal:
    symbol: str
    name: str
    latest_close: float
    day_change: float
    change_5d: float
    change_20d: float
    drawdown_20d: float
    rebound_from_low_20d: float
    ma5: float
    ma10: float
    ma20: float
    ma60: float
    volume_ratio: float
    avg_amount_5d: float
    risk_status: str


def pct_change(current: float, previous: float) -> float:
    return (current / previous - 1) if previous else 0.0


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


class ScreenerService:
    def __init__(self) -> None:
        self._cache: tuple[datetime, list[StockSignal]] | None = None

    def results(self, list_type: str) -> list[ScreenerResult]:
        normalized_type = "rebound" if list_type == "rebound" else "trend"
        signals = self._signals()
        scored = [
            self._rebound_result(signal) if normalized_type == "rebound" else self._trend_result(signal)
            for signal in signals
            if not signal.risk_status.startswith("过滤")
        ]
        return sorted(scored, key=lambda row: row.score, reverse=True)[:8]

    def _signals(self) -> list[StockSignal]:
        if self._cache and (datetime.now() - self._cache[0]).total_seconds() < 300:
            return self._cache[1]

        signals: list[StockSignal] = []
        for symbol in self._pool():
            try:
                bars = market_data.bars(symbol=symbol, period="daily")
                signal = self._analyze(symbol=symbol, bars=bars)
                if signal:
                    signals.append(signal)
            except Exception:
                continue
        self._cache = (datetime.now(), signals)
        return signals

    def _pool(self) -> list[str]:
        configured = os.getenv("SCREENER_SYMBOLS", "")
        symbols = [item.strip() for item in configured.split(",") if item.strip()] or DEFAULT_POOL
        seen: set[str] = set()
        return [symbol for symbol in symbols if not (symbol in seen or seen.add(symbol))]

    def _analyze(self, symbol: str, bars: list[PriceBar]) -> StockSignal | None:
        if len(bars) < 25:
            return None
        usable = bars[-90:]
        closes = [bar.close for bar in usable]
        amounts = [bar.amount for bar in usable]
        latest = usable[-1]
        close = latest.close
        name = market_data.name(symbol)
        day_change = pct_change(close, usable[-2].close) if len(usable) >= 2 else 0.0
        change_5d = pct_change(close, usable[-6].close) if len(usable) >= 6 else day_change
        change_20d = pct_change(close, usable[-21].close) if len(usable) >= 21 else change_5d
        high_20d = max(bar.high for bar in usable[-20:])
        low_20d = min(bar.low for bar in usable[-20:])
        drawdown_20d = close / high_20d - 1 if high_20d else 0.0
        rebound_from_low = close / low_20d - 1 if low_20d else 0.0
        ma5 = average(closes[-5:])
        ma10 = average(closes[-10:])
        ma20 = average(closes[-20:])
        ma60 = average(closes[-60:]) if len(closes) >= 60 else ma20
        avg_amount_5d = average(amounts[-5:])
        avg_amount_20d = average(amounts[-20:])
        volume_ratio = avg_amount_5d / avg_amount_20d if avg_amount_20d else 1.0
        risk_status = self._risk_status(name=name, close=close, avg_amount_5d=avg_amount_5d, bars=usable)
        return StockSignal(
            symbol=symbol,
            name=name,
            latest_close=close,
            day_change=day_change,
            change_5d=change_5d,
            change_20d=change_20d,
            drawdown_20d=drawdown_20d,
            rebound_from_low_20d=rebound_from_low,
            ma5=ma5,
            ma10=ma10,
            ma20=ma20,
            ma60=ma60,
            volume_ratio=volume_ratio,
            avg_amount_5d=avg_amount_5d,
            risk_status=risk_status,
        )

    def _risk_status(self, name: str, close: float, avg_amount_5d: float, bars: list[PriceBar]) -> str:
        if "ST" in name.upper() or "退" in name:
            return "过滤：ST/退市风险"
        if len(bars) < 60:
            return "观察：样本不足 60 日"
        if avg_amount_5d < 30_000_000:
            return "观察：流动性偏弱"
        if close <= 1.5:
            return "观察：低价高波动"
        return "通过"

    def _trend_result(self, signal: StockSignal) -> ScreenerResult:
        ma_alignment = signal.ma5 > signal.ma10 > signal.ma20
        above_ma60 = signal.latest_close > signal.ma60
        near_high = signal.drawdown_20d > -0.04
        score = 40
        score += min(18, max(0, int(signal.change_5d * 180)))
        score += min(20, max(0, int(signal.change_20d * 110)))
        score += 14 if ma_alignment else 0
        score += 8 if above_ma60 else 0
        score += min(10, max(0, int((signal.volume_ratio - 1) * 16)))
        score += 8 if near_high else 0
        if signal.risk_status != "通过":
            score -= 8
        reason = " / ".join(
            [
                f"5日{signal.change_5d * 100:+.1f}%",
                f"20日{signal.change_20d * 100:+.1f}%",
                "均线多头" if ma_alignment else "均线未完全多头",
                f"量能{signal.volume_ratio:.1f}倍",
            ]
        )
        return ScreenerResult(
            list_type="trend",
            symbol=signal.symbol,
            name=signal.name,
            score=max(0, min(100, score)),
            change_pct=round(signal.day_change * 100, 2),
            reason=reason,
            risk_status=signal.risk_status,
            generated_at=datetime.now(),
        )

    def _rebound_result(self, signal: StockSignal) -> ScreenerResult:
        below_ma20 = signal.latest_close < signal.ma20
        stabilizing = signal.day_change > 0 and signal.rebound_from_low_20d > 0.025
        deep_drawdown = signal.drawdown_20d < -0.08
        score = 35
        score += min(24, max(0, int(abs(signal.drawdown_20d) * 150))) if deep_drawdown else 0
        score += min(16, max(0, int(signal.rebound_from_low_20d * 120)))
        score += 12 if stabilizing else 0
        score += 10 if below_ma20 else 0
        score += min(10, max(0, int((signal.volume_ratio - 1) * 14)))
        if signal.change_20d > 0.12:
            score -= 15
        if signal.risk_status != "通过":
            score -= 8
        reason = " / ".join(
            [
                f"距20日高点{signal.drawdown_20d * 100:.1f}%",
                f"离20日低点{signal.rebound_from_low_20d * 100:+.1f}%",
                "日线止跌" if stabilizing else "等待止跌确认",
                f"量能{signal.volume_ratio:.1f}倍",
            ]
        )
        return ScreenerResult(
            list_type="rebound",
            symbol=signal.symbol,
            name=signal.name,
            score=max(0, min(100, score)),
            change_pct=round(signal.day_change * 100, 2),
            reason=reason,
            risk_status=signal.risk_status,
            generated_at=datetime.now(),
        )


screener_service = ScreenerService()
