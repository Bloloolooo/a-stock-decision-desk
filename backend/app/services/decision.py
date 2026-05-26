from datetime import datetime

from app.schemas import ChipLevel, DecisionAdvice, DecisionCenter, IndicatorPoint, IntradayGame, PriceBar
from app.services.market_data import market_data


def _ma(values: list[float], window: int) -> float:
    if not values:
        return 0.0
    scoped = values[-window:]
    return sum(scoped) / len(scoped)


def _ema(values: list[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (span + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(value * alpha + result[-1] * (1 - alpha))
    return result


def _macd(bars: list[PriceBar]) -> list[IndicatorPoint]:
    closes = [bar.close for bar in bars]
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif = [fast - slow for fast, slow in zip(ema12, ema26, strict=False)]
    dea = _ema(dif, 9)
    hist = [(d - s) * 2 for d, s in zip(dif, dea, strict=False)]
    return [
        IndicatorPoint(timestamp=bar.timestamp, value=round(dif[index], 4), signal=round(dea[index], 4), histogram=round(hist[index], 4))
        for index, bar in enumerate(bars[-80:])
    ]


def _kdj(bars: list[PriceBar]) -> list[IndicatorPoint]:
    points: list[IndicatorPoint] = []
    k = 50.0
    d = 50.0
    for index, bar in enumerate(bars):
        window = bars[max(0, index - 8) : index + 1]
        low = min(item.low for item in window)
        high = max(item.high for item in window)
        rsv = 50.0 if high == low else (bar.close - low) / (high - low) * 100
        k = k * 2 / 3 + rsv / 3
        d = d * 2 / 3 + k / 3
        j = 3 * k - 2 * d
        points.append(IndicatorPoint(timestamp=bar.timestamp, k=round(k, 2), d=round(d, 2), j=round(j, 2)))
    return points[-80:]


def _chip_levels(bars: list[PriceBar]) -> list[ChipLevel]:
    scoped = bars[-90:]
    if not scoped:
        return []
    low = min(bar.low for bar in scoped)
    high = max(bar.high for bar in scoped)
    if high <= low:
        return [ChipLevel(price=round(scoped[-1].close, 2), volume_ratio=1.0, label="成交密集")]
    bucket_count = 18
    buckets = [0.0 for _ in range(bucket_count)]
    step = (high - low) / bucket_count
    for bar in scoped:
        typical = (bar.high + bar.low + bar.close) / 3
        index = min(bucket_count - 1, max(0, int((typical - low) / step)))
        buckets[index] += bar.volume
    total = sum(buckets) or 1.0
    ranked = sorted(enumerate(buckets), key=lambda item: item[1], reverse=True)[:5]
    levels = []
    for index, volume in sorted(ranked, key=lambda item: item[0]):
        price = low + step * (index + 0.5)
        levels.append(ChipLevel(price=round(price, 2), volume_ratio=round(volume / total, 4), label="成交密集"))
    return levels


def _intraday_game(bars: list[PriceBar]) -> IntradayGame:
    if not bars:
        return IntradayGame(status="等待分时", buy_power_pct=0, sell_power_pct=0, vwap=0, price_vs_vwap_pct=0, description="暂无分时数据")
    buy_volume = 0.0
    sell_volume = 0.0
    amount = 0.0
    volume = 0.0
    previous_close = bars[0].open
    for bar in bars:
        if bar.close >= previous_close:
            buy_volume += bar.volume
        else:
            sell_volume += bar.volume
        amount += bar.amount
        volume += bar.volume
        previous_close = bar.close
    total = buy_volume + sell_volume or 1.0
    vwap = amount / volume if volume else bars[-1].close
    price_vs_vwap = (bars[-1].close / vwap - 1) * 100 if vwap else 0.0
    buy_power = buy_volume / total * 100
    sell_power = sell_volume / total * 100
    if buy_power >= 58 and price_vs_vwap > 0:
        status = "多方占优"
    elif sell_power >= 56 and price_vs_vwap < 0:
        status = "空方占优"
    elif bars[-1].close < max(bar.high for bar in bars) * 0.985 and buy_power >= 50:
        status = "拉高回落"
    else:
        status = "均衡博弈"
    return IntradayGame(
        status=status,
        buy_power_pct=round(buy_power, 1),
        sell_power_pct=round(sell_power, 1),
        vwap=round(vwap, 2),
        price_vs_vwap_pct=round(price_vs_vwap, 2),
        description=f"{status}，现价较 VWAP {price_vs_vwap:+.2f}%。",
    )


class DecisionService:
    def decision(self, symbol: str) -> DecisionCenter:
        daily = market_data.bars(symbol=symbol, period="daily")
        intraday = market_data.bars(symbol=symbol, period="intraday")
        usable = daily[-120:] if len(daily) >= 30 else daily
        closes = [bar.close for bar in usable]
        last = usable[-1]
        ma5 = _ma(closes, 5)
        ma20 = _ma(closes, 20)
        ma60 = _ma(closes, 60)
        avg_volume_5 = _ma([bar.volume for bar in usable[:-1]], 5)
        avg_volume_20 = _ma([bar.volume for bar in usable[:-1]], 20)
        volume_ratio = last.volume / avg_volume_5 if avg_volume_5 else 1.0
        support = min(bar.low for bar in usable[-20:])
        resistance = max(bar.high for bar in usable[-20:])
        macd_points = _macd(usable)
        kdj_points = _kdj(usable)
        latest_macd = macd_points[-1]
        latest_kdj = kdj_points[-1]

        trend_status = self._trend_status(last.close, ma5, ma20, ma60)
        volume_status = self._volume_status(volume_ratio, last.amount, avg_volume_20 * last.close)
        macd_status = self._macd_status(latest_macd)
        kdj_status = self._kdj_status(latest_kdj)
        game = _intraday_game(intraday[-300:])
        chips = _chip_levels(usable)
        advice = self._advice(trend_status, volume_status, macd_status, kdj_status, game, last.close, support, resistance)

        return DecisionCenter(
            symbol=symbol,
            name=market_data.name(symbol),
            current_price=round(last.close, 2),
            trend_status=trend_status,
            volume_status=volume_status,
            volume_ratio=round(volume_ratio, 2),
            turnover_rate=last.turnover_rate,
            support_price=round(support, 2),
            resistance_price=round(resistance, 2),
            macd_status=macd_status,
            kdj_status=kdj_status,
            intraday_game=game,
            chips=chips,
            macd=macd_points,
            kdj=kdj_points,
            advice=advice,
            updated_at=datetime.now(),
        )

    def _trend_status(self, close: float, ma5: float, ma20: float, ma60: float) -> str:
        if close > ma5 > ma20 > ma60:
            return "强趋势"
        if close > ma20 and ma5 > ma20:
            return "趋势修复"
        if close < ma20 < ma60:
            return "弱势"
        return "震荡"

    def _volume_status(self, ratio: float, amount: float, avg_amount_20: float) -> str:
        if ratio >= 1.8:
            return "异常放量"
        if ratio >= 1.25:
            return "温和放量"
        if ratio <= 0.65:
            return "缩量"
        if amount > avg_amount_20 * 1.1:
            return "量能活跃"
        return "量能平稳"

    def _macd_status(self, point: IndicatorPoint) -> str:
        if (point.value or 0) > (point.signal or 0) and (point.histogram or 0) > 0:
            return "金叉偏多"
        if (point.value or 0) < (point.signal or 0) and (point.histogram or 0) < 0:
            return "死叉偏空"
        return "钝化观察"

    def _kdj_status(self, point: IndicatorPoint) -> str:
        k = point.k or 0
        d = point.d or 0
        j = point.j or 0
        if j >= 90:
            return "高位超买"
        if j <= 15:
            return "低位超卖"
        if k > d:
            return "短线偏多"
        return "短线偏弱"

    def _advice(
        self,
        trend: str,
        volume: str,
        macd: str,
        kdj: str,
        game: IntradayGame,
        close: float,
        support: float,
        resistance: float,
    ) -> DecisionAdvice:
        score = 50
        reasons: list[str] = []
        warnings: list[str] = []
        for label, delta in [(trend, {"强趋势": 18, "趋势修复": 10, "震荡": 0, "弱势": -16}.get(trend, 0)), (volume, {"温和放量": 8, "量能活跃": 5, "异常放量": -4, "缩量": -6}.get(volume, 0)), (macd, {"金叉偏多": 10, "死叉偏空": -10}.get(macd, 0)), (kdj, {"短线偏多": 6, "低位超卖": 4, "高位超买": -8, "短线偏弱": -5}.get(kdj, 0)), (game.status, {"多方占优": 8, "空方占优": -8, "拉高回落": -6}.get(game.status, 0))]:
            score += delta
            reasons.append(f"{label}：{delta:+d} 分")
        if close > resistance * 0.97:
            warnings.append("价格接近 20 日压力区，追高需要等待放量确认。")
        if close < support * 1.03:
            reasons.append("靠近 20 日支撑区，适合观察承接。")
        if volume == "异常放量" and game.status != "多方占优":
            warnings.append("放量但分时多方不强，警惕冲高回落。")
        confidence = max(0, min(100, round(score)))
        if confidence >= 72:
            action = "可买/可加仓"
        elif confidence >= 58:
            action = "持有观察"
        elif confidence >= 45:
            action = "观望"
        else:
            action = "减仓/规避"
        return DecisionAdvice(action=action, confidence=confidence, reasons=reasons, warnings=warnings)


decision_service = DecisionService()
