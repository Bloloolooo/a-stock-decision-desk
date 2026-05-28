from dataclasses import dataclass
from datetime import datetime
import json
import os
from sqlite3 import Row
import threading
import time

from app.db import get_connection, init_db
from app.schemas import PriceBar, ScreenerConfig, ScreenerResult, ScreenerStatus
from app.services.market_data import market_data, stock_universe


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
    volatility_20d: float
    atr_ratio_14d: float
    up_days_5d: int
    down_days_5d: int
    breakout_20d: bool
    pullback_to_ma20: bool
    risk_status: str


def pct_change(current: float, previous: float) -> float:
    return (current / previous - 1) if previous else 0.0


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def true_range(current: PriceBar, previous: PriceBar) -> float:
    return max(current.high - current.low, abs(current.high - previous.close), abs(current.low - previous.close))


def signal_direction(values: list[float]) -> int:
    if len(values) < 2:
        return 0
    return sum(1 if values[index] >= values[index - 1] else -1 for index in range(1, len(values)))


def factor(name: str, value: str, contribution: int | float, status: str) -> dict[str, str | int | float]:
    return {
        "name": name,
        "value": value,
        "contribution": contribution,
        "status": status,
    }


class ScreenerService:
    def __init__(self) -> None:
        init_db()
        self._cache: tuple[datetime, list[StockSignal]] | None = None
        self._last_duration_seconds: float | None = None
        self._last_error_count = 0
        self._scan_lock = threading.Lock()
        self._universe_cache: tuple[datetime, list[str]] | None = None

    def results(self, list_type: str) -> list[ScreenerResult]:
        normalized_type = list_type if list_type in {"balanced", "trend", "rebound"} else "balanced"
        cached = self._cached_results(normalized_type)
        if cached:
            return cached
        self._scan_symbols(self._pool(), scope=self._scope(), persist=True)
        return self._cached_results(normalized_type)

    def refresh(self) -> ScreenerStatus:
        self.start_full_scan()
        return self.status()

    def start_full_scan(self) -> ScreenerStatus:
        if self._scan_lock.locked():
            return self.status()
        symbols = self._pool()
        self._update_scan_state(
            status="queued",
            scope=self._scope(),
            total_count=len(symbols),
            processed_count=0,
            success_count=0,
            error_count=0,
            market_environment="待判断",
            market_factor=1.0,
            last_error=None,
            started=False,
            finished=False,
        )
        thread = threading.Thread(target=self._run_background_scan, daemon=True)
        thread.start()
        return self.status()

    def config(self) -> ScreenerConfig:
        with get_connection() as connection:
            row = connection.execute("SELECT symbols, updated_at FROM screener_config WHERE id = 1").fetchone()
        return self._config_from_row(row)

    def update_config(self, symbols: list[str]) -> ScreenerConfig:
        normalized_symbols = self._normalize_symbols(symbols)
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO screener_config (id, symbols, updated_at)
                VALUES (1, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET symbols = excluded.symbols, updated_at = excluded.updated_at
                """,
                (",".join(normalized_symbols),),
            )
        self.start_full_scan()
        self._cache = None
        return self.config()

    def status(self) -> ScreenerStatus:
        state = self._scan_state()
        last_scan_at = state["finished_at"]
        cache_age = int((datetime.now() - last_scan_at).total_seconds()) if last_scan_at else None
        symbols = self._pool()
        return ScreenerStatus(
            pool_size=len(symbols),
            cache_age_seconds=cache_age,
            last_scan_at=last_scan_at,
            last_duration_seconds=state["last_duration_seconds"],
            last_error_count=state["error_count"],
            symbols=symbols,
            scan_status=state["status"],
            scope=state["scope"],
            total_count=state["total_count"],
            processed_count=state["processed_count"],
            success_count=state["success_count"],
            market_environment=state["market_environment"],
            market_factor=state["market_factor"],
            last_error=state["last_error"],
        )

    def _run_background_scan(self) -> None:
        if not self._scan_lock.acquire(blocking=False):
            return
        try:
            self._scan_symbols(self._pool(), scope=self._scope(), persist=True)
        finally:
            self._scan_lock.release()

    def _scan_symbols(self, symbols: list[str], scope: str, persist: bool) -> list[StockSignal]:
        started_at = time.perf_counter()
        signals: list[StockSignal] = []
        error_count = 0
        environment, market_factor = self._market_environment()
        self._update_scan_state(
            status="running",
            scope=scope,
            total_count=len(symbols),
            processed_count=0,
            success_count=0,
            error_count=0,
            market_environment=environment,
            market_factor=market_factor,
            last_error=None,
            started=True,
            finished=False,
        )
        for index, symbol in enumerate(symbols, start=1):
            try:
                bars = market_data.bars(symbol=symbol, period="daily")
                signal = self._analyze(symbol=symbol, bars=bars)
                if signal:
                    signals.append(signal)
            except Exception as exc:
                error_count += 1
                self._update_scan_state(
                    status="running",
                    scope=scope,
                    total_count=len(symbols),
                    processed_count=index,
                    success_count=len(signals),
                    error_count=error_count,
                    market_environment=environment,
                    market_factor=market_factor,
                    last_error=str(exc)[-240:],
                    started=False,
                    finished=False,
                )
                continue
            if index == len(symbols) or index % 20 == 0:
                self._update_scan_state(
                    status="running",
                    scope=scope,
                    total_count=len(symbols),
                    processed_count=index,
                    success_count=len(signals),
                    error_count=error_count,
                    market_environment=environment,
                    market_factor=market_factor,
                    last_error=None,
                    started=False,
                    finished=False,
                )
        self._last_duration_seconds = round(time.perf_counter() - started_at, 2)
        self._last_error_count = error_count
        if persist:
            self._persist_results(signals, market_factor)
        self._cache = (datetime.now(), signals)
        self._update_scan_state(
            status="ready",
            scope=scope,
            total_count=len(symbols),
            processed_count=len(symbols),
            success_count=len(signals),
            error_count=error_count,
            market_environment=environment,
            market_factor=market_factor,
            last_error=None,
            started=False,
            finished=True,
            duration=self._last_duration_seconds,
        )
        return signals

    def _pool(self) -> list[str]:
        env_symbols = self._normalize_symbols(os.getenv("SCREENER_SYMBOLS", "").split(","))
        symbols = env_symbols or self._full_market_symbols()
        if not symbols:
            symbols = DEFAULT_POOL
        max_symbols = int(os.getenv("SCREENER_MAX_SYMBOLS", "0") or "0")
        if max_symbols > 0:
            symbols = symbols[:max_symbols]
        return self._normalize_symbols(symbols)

    def _core_pool(self) -> list[str]:
        return self._normalize_symbols(DEFAULT_POOL)

    def _full_market_symbols(self) -> list[str]:
        if self._universe_cache and (datetime.now() - self._universe_cache[0]).total_seconds() < 3600:
            return self._universe_cache[1]
        try:
            symbols = self._normalize_symbols([stock.symbol for stock in stock_universe()])
        except Exception:
            symbols = self._core_pool()
        self._universe_cache = (datetime.now(), symbols)
        return symbols

    def _scope(self) -> str:
        env_symbols = self._normalize_symbols(os.getenv("SCREENER_SYMBOLS", "").split(","))
        return "env_limited" if env_symbols else "full_market"

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for symbol in symbols:
            cleaned = "".join(ch for ch in symbol.strip() if ch.isdigit())
            if len(cleaned) == 6 and cleaned not in seen:
                seen.add(cleaned)
                normalized.append(cleaned)
        return normalized

    def _config_from_row(self, row: Row | None) -> ScreenerConfig:
        if not row:
            return ScreenerConfig(symbols=[], updated_at=datetime.now())
        symbols = self._normalize_symbols(str(row["symbols"]).split(","))
        return ScreenerConfig(symbols=symbols, updated_at=datetime.fromisoformat(row["updated_at"]))

    def _cached_results(self, list_type: str) -> list[ScreenerResult]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT list_type, symbol, name, score, change_pct, reason, risk_status, factors_json, generated_at
                FROM screener_results
                WHERE list_type = ?
                ORDER BY score DESC, symbol
                LIMIT 12
                """,
                (list_type,),
            ).fetchall()
        return [
            ScreenerResult(
                list_type=row["list_type"],
                symbol=row["symbol"],
                name=row["name"],
                score=int(row["score"]),
                change_pct=float(row["change_pct"]),
                reason=row["reason"],
                risk_status=row["risk_status"],
                factors=json.loads(row["factors_json"]),
                generated_at=datetime.fromisoformat(row["generated_at"]),
            )
            for row in rows
        ]

    def _persist_results(self, signals: list[StockSignal], market_factor: float) -> None:
        generated_at = datetime.now()
        rows: list[ScreenerResult] = []
        for signal in signals:
            if signal.risk_status.startswith("过滤"):
                continue
            rows.append(self._balanced_result(signal, market_factor=market_factor))
            rows.append(self._trend_result(signal, market_factor=market_factor))
            rows.append(self._rebound_result(signal, market_factor=market_factor))
        ranked = []
        for list_type in ("balanced", "trend", "rebound"):
            ranked.extend(sorted((row for row in rows if row.list_type == list_type), key=lambda row: row.score, reverse=True)[:80])
        with get_connection() as connection:
            connection.execute("DELETE FROM screener_results")
            connection.executemany(
                """
                INSERT INTO screener_results (
                    list_type, symbol, name, score, change_pct, reason, risk_status, factors_json, generated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row.list_type,
                        row.symbol,
                        row.name,
                        row.score,
                        row.change_pct,
                        row.reason,
                        row.risk_status,
                        json.dumps(row.factors, ensure_ascii=False),
                        generated_at.isoformat(),
                    )
                    for row in ranked
                ],
            )

    def _scan_state(self) -> dict:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT status, scope, total_count, processed_count, success_count, error_count,
                       market_environment, market_factor, last_error, started_at, finished_at, updated_at
                FROM screener_scan_state WHERE id = 1
                """
            ).fetchone()
        if not row:
            return {
                "status": "idle",
                "scope": "default",
                "total_count": 0,
                "processed_count": 0,
                "success_count": 0,
                "error_count": 0,
                "market_environment": "未知",
                "market_factor": 1.0,
                "last_error": None,
                "finished_at": None,
                "last_duration_seconds": None,
            }
        started_at = datetime.fromisoformat(row["started_at"]) if row["started_at"] else None
        finished_at = datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None
        return {
            "status": row["status"],
            "scope": row["scope"],
            "total_count": int(row["total_count"]),
            "processed_count": int(row["processed_count"]),
            "success_count": int(row["success_count"]),
            "error_count": int(row["error_count"]),
            "market_environment": row["market_environment"],
            "market_factor": float(row["market_factor"]),
            "last_error": row["last_error"],
            "finished_at": finished_at,
            "last_duration_seconds": round((finished_at - started_at).total_seconds(), 2) if started_at and finished_at else None,
        }

    def _update_scan_state(
        self,
        status: str,
        scope: str,
        total_count: int,
        processed_count: int,
        success_count: int,
        error_count: int,
        market_environment: str,
        market_factor: float,
        last_error: str | None,
        started: bool,
        finished: bool,
        duration: float | None = None,
    ) -> None:
        del duration
        started_at = "datetime('now')" if started else "started_at"
        finished_at = "datetime('now')" if finished else "finished_at"
        with get_connection() as connection:
            connection.execute(
                f"""
                UPDATE screener_scan_state
                SET status = ?, scope = ?, total_count = ?, processed_count = ?, success_count = ?,
                    error_count = ?, market_environment = ?, market_factor = ?, last_error = ?,
                    started_at = {started_at}, finished_at = {finished_at}, updated_at = datetime('now')
                WHERE id = 1
                """,
                (
                    status,
                    scope,
                    total_count,
                    processed_count,
                    success_count,
                    error_count,
                    market_environment,
                    market_factor,
                    last_error,
                ),
            )

    def _market_environment(self) -> tuple[str, float]:
        indexes = ["000300", "000001", "399006"]
        scores: list[int] = []
        for symbol in indexes:
            try:
                bars = market_data.bars(symbol=symbol, period="daily")
            except Exception:
                continue
            if len(bars) < 60:
                continue
            closes = [bar.close for bar in bars[-90:]]
            close = closes[-1]
            ma20 = average(closes[-20:])
            ma60 = average(closes[-60:])
            if close > ma20 > ma60:
                scores.append(1)
            elif close < ma20 < ma60:
                scores.append(-1)
            else:
                scores.append(0)
        total = sum(scores)
        if total >= 2:
            return "强势", 1.08
        if total <= -2:
            return "弱势", 0.86
        return "震荡", 1.0

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
        daily_returns = [pct_change(closes[index], closes[index - 1]) for index in range(max(1, len(closes) - 20), len(closes))]
        return_mean = average(daily_returns)
        volatility_20d = (average([(value - return_mean) ** 2 for value in daily_returns]) ** 0.5) if daily_returns else 0.0
        tr_values = [true_range(usable[index], usable[index - 1]) for index in range(max(1, len(usable) - 14), len(usable))]
        atr_ratio_14d = average(tr_values) / close if close else 0.0
        recent_closes = closes[-6:]
        up_days_5d = sum(1 for index in range(1, len(recent_closes)) if recent_closes[index] > recent_closes[index - 1])
        down_days_5d = sum(1 for index in range(1, len(recent_closes)) if recent_closes[index] < recent_closes[index - 1])
        previous_high_20d = max(bar.high for bar in usable[-21:-1]) if len(usable) >= 21 else high_20d
        breakout_20d = latest.close >= previous_high_20d * 0.995 and latest.close >= latest.open
        pullback_to_ma20 = ma20 > 0 and abs(close / ma20 - 1) <= 0.025 and signal_direction(closes[-5:]) >= 0
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
            volatility_20d=volatility_20d,
            atr_ratio_14d=atr_ratio_14d,
            up_days_5d=up_days_5d,
            down_days_5d=down_days_5d,
            breakout_20d=breakout_20d,
            pullback_to_ma20=pullback_to_ma20,
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

    def _balanced_result(self, signal: StockSignal, market_factor: float = 1.0) -> ScreenerResult:
        trend_base = signal.change_20d > 0 and signal.latest_close > signal.ma20
        healthy_momentum = -0.03 <= signal.change_5d <= 0.12
        volume_score = min(12, max(-6, int((signal.volume_ratio - 1) * 14)))
        trend_score = min(18, max(-8, int(signal.change_20d * 100)))
        position_score = 12 if signal.latest_close > signal.ma20 else -6
        ma_score = 10 if signal.ma5 >= signal.ma10 >= signal.ma20 else 0
        breakout_score = 8 if signal.breakout_20d else 0
        pullback_score = 8 if signal.pullback_to_ma20 else 0
        momentum_score = 8 if healthy_momentum else -8
        volatility_penalty = -12 if signal.atr_ratio_14d > 0.075 or signal.volatility_20d > 0.055 else 0
        streak_penalty = -8 if signal.down_days_5d >= 4 else 0
        chase_penalty = -10 if signal.change_5d > 0.18 and signal.volume_ratio < 1.15 else 0
        risk_penalty = -10 if signal.risk_status != "通过" else 0
        score = 48
        score += (
            trend_score
            + position_score
            + ma_score
            + volume_score
            + breakout_score
            + pullback_score
            + momentum_score
            + volatility_penalty
            + streak_penalty
            + chase_penalty
            + risk_penalty
        )
        score = int(score * min(1.06, max(0.9, market_factor)))
        style = "趋势突破" if signal.breakout_20d else "缩量回踩" if signal.pullback_to_ma20 else "均衡观察"
        if not trend_base and signal.drawdown_20d < -0.08:
            style = "低位修复"
        reason = " / ".join(
            [
                style,
                f"20日{signal.change_20d * 100:+.1f}%",
                f"ATR{signal.atr_ratio_14d * 100:.1f}%",
                f"量能{signal.volume_ratio:.1f}倍",
            ]
        )
        factors = [
            factor("入选类型", style, 0, "综合风格"),
            factor("20日趋势", f"{signal.change_20d * 100:+.1f}%", trend_score, "中短期方向"),
            factor("MA20位置", "站上MA20" if signal.latest_close > signal.ma20 else "低于MA20", position_score, "趋势生命线"),
            factor("均线结构", "MA5>=MA10>=MA20" if signal.ma5 >= signal.ma10 >= signal.ma20 else "结构一般", ma_score, "趋势质量"),
            factor("放量突破", "接近20日新高" if signal.breakout_20d else "未突破", breakout_score, "突破确认"),
            factor("缩量回踩", "贴近MA20" if signal.pullback_to_ma20 else "无回踩结构", pullback_score, "低吸观察"),
            factor("量能", f"{signal.volume_ratio:.1f}倍", volume_score, "资金参与"),
            factor("波动风险", f"ATR {signal.atr_ratio_14d * 100:.1f}%", volatility_penalty, "过高扣分"),
            factor("连续下跌", f"{signal.down_days_5d}天", streak_penalty, "未止跌扣分"),
            factor("追高风险", f"5日{signal.change_5d * 100:+.1f}%", chase_penalty, "急涨缩量扣分"),
            factor("风险过滤", signal.risk_status, risk_penalty, "风险扣分"),
            factor("市场环境", f"{market_factor:.2f}x", round((market_factor - 1) * 100, 1), "大盘趋势系数"),
        ]
        return ScreenerResult(
            list_type="balanced",
            symbol=signal.symbol,
            name=signal.name,
            score=max(0, min(100, score)),
            change_pct=round(signal.day_change * 100, 2),
            reason=reason,
            risk_status=signal.risk_status,
            factors=factors,
            generated_at=datetime.now(),
        )

    def _trend_result(self, signal: StockSignal, market_factor: float = 1.0) -> ScreenerResult:
        ma_alignment = signal.ma5 > signal.ma10 > signal.ma20
        above_ma60 = signal.latest_close > signal.ma60
        near_high = signal.drawdown_20d > -0.04
        change_5d_score = min(18, max(0, int(signal.change_5d * 180)))
        change_20d_score = min(20, max(0, int(signal.change_20d * 110)))
        ma_score = 14 if ma_alignment else 0
        ma60_score = 8 if above_ma60 else 0
        volume_score = min(10, max(0, int((signal.volume_ratio - 1) * 16)))
        near_high_score = 8 if near_high else 0
        breakout_score = 8 if signal.breakout_20d else 0
        volatility_penalty = -10 if signal.atr_ratio_14d > 0.08 else 0
        chase_penalty = -8 if signal.change_5d > 0.2 and signal.volume_ratio < 1.1 else 0
        risk_penalty = -8 if signal.risk_status != "通过" else 0
        score = 40
        score += change_5d_score + change_20d_score + ma_score + ma60_score + volume_score + near_high_score + breakout_score + volatility_penalty + chase_penalty + risk_penalty
        score = int(score * market_factor)
        reason = " / ".join(
            [
                f"5日{signal.change_5d * 100:+.1f}%",
                f"20日{signal.change_20d * 100:+.1f}%",
                "均线多头" if ma_alignment else "均线未完全多头",
                f"量能{signal.volume_ratio:.1f}倍",
            ]
        )
        factors = [
            factor("5日涨幅", f"{signal.change_5d * 100:+.1f}%", change_5d_score, "越强越好"),
            factor("20日涨幅", f"{signal.change_20d * 100:+.1f}%", change_20d_score, "确认波段强度"),
            factor("均线结构", "MA5 > MA10 > MA20" if ma_alignment else "未完全多头", ma_score, "趋势排列"),
            factor("MA60位置", "站上MA60" if above_ma60 else "未站上MA60", ma60_score, "中期趋势"),
            factor("量能", f"{signal.volume_ratio:.1f}倍", volume_score, "5日均额/20日均额"),
            factor("20日高位", f"{signal.drawdown_20d * 100:.1f}%", near_high_score, "接近强势高位"),
            factor("放量突破", "接近20日新高" if signal.breakout_20d else "未突破", breakout_score, "突破确认"),
            factor("波动风险", f"ATR {signal.atr_ratio_14d * 100:.1f}%", volatility_penalty, "过高扣分"),
            factor("追高风险", f"5日{signal.change_5d * 100:+.1f}%", chase_penalty, "急涨缩量扣分"),
            factor("风险过滤", signal.risk_status, risk_penalty, "风险扣分"),
            factor("市场环境", f"{market_factor:.2f}x", round((market_factor - 1) * 100, 1), "大盘趋势系数"),
        ]
        return ScreenerResult(
            list_type="trend",
            symbol=signal.symbol,
            name=signal.name,
            score=max(0, min(100, score)),
            change_pct=round(signal.day_change * 100, 2),
            reason=reason,
            risk_status=signal.risk_status,
            factors=factors,
            generated_at=datetime.now(),
        )

    def _rebound_result(self, signal: StockSignal, market_factor: float = 1.0) -> ScreenerResult:
        below_ma20 = signal.latest_close < signal.ma20
        stabilizing = signal.day_change > 0 and signal.rebound_from_low_20d > 0.025
        deep_drawdown = signal.drawdown_20d < -0.08
        drawdown_score = min(24, max(0, int(abs(signal.drawdown_20d) * 150))) if deep_drawdown else 0
        rebound_score = min(16, max(0, int(signal.rebound_from_low_20d * 120)))
        stabilizing_score = 12 if stabilizing else 0
        ma20_score = 10 if below_ma20 else 0
        volume_score = min(10, max(0, int((signal.volume_ratio - 1) * 14)))
        overheated_penalty = -15 if signal.change_20d > 0.12 else 0
        down_streak_penalty = -8 if signal.down_days_5d >= 4 else 0
        volatility_penalty = -8 if signal.atr_ratio_14d > 0.09 else 0
        risk_penalty = -8 if signal.risk_status != "通过" else 0
        score = 35
        score += drawdown_score + rebound_score + stabilizing_score + ma20_score + volume_score + overheated_penalty + down_streak_penalty + volatility_penalty + risk_penalty
        rebound_factor = min(1.05, max(0.9, market_factor + 0.02 if market_factor < 1 else market_factor - 0.03))
        score = int(score * rebound_factor)
        reason = " / ".join(
            [
                f"距20日高点{signal.drawdown_20d * 100:.1f}%",
                f"离20日低点{signal.rebound_from_low_20d * 100:+.1f}%",
                "日线止跌" if stabilizing else "等待止跌确认",
                f"量能{signal.volume_ratio:.1f}倍",
            ]
        )
        factors = [
            factor("20日回撤", f"{signal.drawdown_20d * 100:.1f}%", drawdown_score, "跌幅充分"),
            factor("离20日低点", f"{signal.rebound_from_low_20d * 100:+.1f}%", rebound_score, "低位修复"),
            factor("止跌信号", "日线止跌" if stabilizing else "等待确认", stabilizing_score, "阳线/低位反弹"),
            factor("MA20乖离", "低于MA20" if below_ma20 else "已回到MA20上方", ma20_score, "仍在低位"),
            factor("量能", f"{signal.volume_ratio:.1f}倍", volume_score, "成交恢复"),
            factor("过热扣分", f"20日{signal.change_20d * 100:+.1f}%", overheated_penalty, "避免追高"),
            factor("连续下跌", f"{signal.down_days_5d}天", down_streak_penalty, "未止跌扣分"),
            factor("波动风险", f"ATR {signal.atr_ratio_14d * 100:.1f}%", volatility_penalty, "过高扣分"),
            factor("风险过滤", signal.risk_status, risk_penalty, "风险扣分"),
            factor("市场环境", f"{rebound_factor:.2f}x", round((rebound_factor - 1) * 100, 1), "大盘趋势系数"),
        ]
        return ScreenerResult(
            list_type="rebound",
            symbol=signal.symbol,
            name=signal.name,
            score=max(0, min(100, score)),
            change_pct=round(signal.day_change * 100, 2),
            reason=reason,
            risk_status=signal.risk_status,
            factors=factors,
            generated_at=datetime.now(),
        )


screener_service = ScreenerService()
