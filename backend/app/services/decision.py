from datetime import datetime

from app.schemas import ChipAnalysis, ChipLevel, DecisionAdvice, DecisionCenter, IndicatorPoint, IndicatorScore, IntradayGame, PriceBar
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


def _rsi(bars: list[PriceBar], window: int = 14) -> list[IndicatorPoint]:
    points: list[IndicatorPoint] = []
    closes = [bar.close for bar in bars]
    for index, bar in enumerate(bars):
        if index == 0:
            points.append(IndicatorPoint(timestamp=bar.timestamp, value=50))
            continue
        scoped = closes[max(1, index - window + 1) : index + 1]
        previous = closes[max(0, index - window) : index]
        gains = [max(0.0, current - prev) for current, prev in zip(scoped, previous, strict=False)]
        losses = [max(0.0, prev - current) for current, prev in zip(scoped, previous, strict=False)]
        avg_gain = sum(gains) / len(gains) if gains else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        value = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
        points.append(IndicatorPoint(timestamp=bar.timestamp, value=round(value, 2)))
    return points[-80:]


def _wr(bars: list[PriceBar], window: int = 14) -> list[IndicatorPoint]:
    points: list[IndicatorPoint] = []
    for index, bar in enumerate(bars):
        scoped = bars[max(0, index - window + 1) : index + 1]
        high = max(item.high for item in scoped)
        low = min(item.low for item in scoped)
        value = -50.0 if high == low else (high - bar.close) / (high - low) * -100
        points.append(IndicatorPoint(timestamp=bar.timestamp, value=round(value, 2)))
    return points[-80:]


def _psy(bars: list[PriceBar], window: int = 12) -> list[IndicatorPoint]:
    points: list[IndicatorPoint] = []
    for index, bar in enumerate(bars):
        if index == 0:
            points.append(IndicatorPoint(timestamp=bar.timestamp, value=50))
            continue
        start = max(1, index - window + 1)
        changes = [bars[item].close > bars[item - 1].close for item in range(start, index + 1)]
        value = sum(1 for item in changes if item) / len(changes) * 100 if changes else 50
        points.append(IndicatorPoint(timestamp=bar.timestamp, value=round(value, 2)))
    return points[-80:]


def _dmi(bars: list[PriceBar], window: int = 14) -> list[IndicatorPoint]:
    if not bars:
        return []
    trs = [0.0]
    plus_dm = [0.0]
    minus_dm = [0.0]
    for index in range(1, len(bars)):
        current = bars[index]
        previous = bars[index - 1]
        up_move = current.high - previous.high
        down_move = previous.low - current.low
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        trs.append(max(current.high - current.low, abs(current.high - previous.close), abs(current.low - previous.close)))
    points: list[IndicatorPoint] = []
    dx_values: list[float] = []
    for index, bar in enumerate(bars):
        start = max(0, index - window + 1)
        tr_sum = sum(trs[start : index + 1]) or 1.0
        pdi = sum(plus_dm[start : index + 1]) / tr_sum * 100
        mdi = sum(minus_dm[start : index + 1]) / tr_sum * 100
        dx = abs(pdi - mdi) / (pdi + mdi) * 100 if pdi + mdi else 0.0
        dx_values.append(dx)
        adx = sum(dx_values[max(0, index - window + 1) : index + 1]) / len(dx_values[max(0, index - window + 1) : index + 1])
        points.append(IndicatorPoint(timestamp=bar.timestamp, pdi=round(pdi, 2), mdi=round(mdi, 2), adx=round(adx, 2)))
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


def _chip_analysis(chips: list[ChipLevel], close: float) -> ChipAnalysis:
    if not chips:
        return ChipAnalysis(status="筹码不足", support_strength=0, pressure_strength=0, description="暂无足够成交密集区数据。")
    support = [chip for chip in chips if chip.price <= close]
    pressure = [chip for chip in chips if chip.price > close]
    support_strength = sum(chip.volume_ratio for chip in support)
    pressure_strength = sum(chip.volume_ratio for chip in pressure)
    nearest_support = max((chip.price for chip in support), default=None)
    nearest_pressure = min((chip.price for chip in pressure), default=None)
    if support_strength >= pressure_strength * 1.25:
        status = "下方支撑占优"
    elif pressure_strength >= support_strength * 1.25:
        status = "上方压力偏重"
    else:
        status = "筹码均衡"
    description = f"{status}，支撑筹码 {support_strength * 100:.1f}%，压力筹码 {pressure_strength * 100:.1f}%。"
    return ChipAnalysis(
        status=status,
        support_strength=round(support_strength, 4),
        pressure_strength=round(pressure_strength, 4),
        nearest_support=round(nearest_support, 2) if nearest_support is not None else None,
        nearest_pressure=round(nearest_pressure, 2) if nearest_pressure is not None else None,
        description=description,
    )


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
        rsi_points = _rsi(usable)
        wr_points = _wr(usable)
        psy_points = _psy(usable)
        dmi_points = _dmi(usable)
        latest_macd = macd_points[-1]
        latest_kdj = kdj_points[-1]
        latest_rsi = rsi_points[-1]
        latest_wr = wr_points[-1]
        latest_psy = psy_points[-1]
        latest_dmi = dmi_points[-1]

        trend_status = self._trend_status(last.close, ma5, ma20, ma60)
        volume_status = self._volume_status(volume_ratio, last.amount, avg_volume_20 * last.close)
        macd_status = self._macd_status(latest_macd)
        kdj_status = self._kdj_status(latest_kdj)
        rsi_status = self._rsi_status(latest_rsi)
        wr_status = self._wr_status(latest_wr)
        psy_status = self._psy_status(latest_psy)
        dmi_status = self._dmi_status(latest_dmi)
        game = _intraday_game(intraday[-300:])
        chips = _chip_levels(usable)
        chip_analysis = _chip_analysis(chips, last.close)
        matrix = self._indicator_matrix(
            trend_status,
            volume_status,
            macd_status,
            kdj_status,
            rsi_status,
            wr_status,
            psy_status,
            dmi_status,
            game,
            chip_analysis,
            latest_rsi,
            latest_wr,
            latest_psy,
            latest_dmi,
        )
        advice = self._advice(matrix, volume_status, game, chip_analysis, last.close, support, resistance)

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
            rsi_status=rsi_status,
            wr_status=wr_status,
            psy_status=psy_status,
            dmi_status=dmi_status,
            intraday_game=game,
            chips=chips,
            chip_analysis=chip_analysis,
            macd=macd_points,
            kdj=kdj_points,
            rsi=rsi_points,
            wr=wr_points,
            psy=psy_points,
            dmi=dmi_points,
            indicator_matrix=matrix,
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

    def _rsi_status(self, point: IndicatorPoint) -> str:
        value = point.value or 50
        if value >= 75:
            return "RSI过热"
        if value <= 25:
            return "RSI超卖"
        if value >= 55:
            return "RSI偏强"
        if value <= 45:
            return "RSI偏弱"
        return "RSI中性"

    def _wr_status(self, point: IndicatorPoint) -> str:
        value = point.value or -50
        if value >= -15:
            return "WR超买"
        if value <= -85:
            return "WR超卖"
        if value >= -35:
            return "WR偏强"
        if value <= -65:
            return "WR偏弱"
        return "WR中性"

    def _psy_status(self, point: IndicatorPoint) -> str:
        value = point.value or 50
        if value >= 75:
            return "情绪过热"
        if value <= 25:
            return "情绪冰点"
        if value >= 58:
            return "情绪偏多"
        if value <= 42:
            return "情绪偏空"
        return "情绪中性"

    def _dmi_status(self, point: IndicatorPoint) -> str:
        pdi = point.pdi or 0
        mdi = point.mdi or 0
        adx = point.adx or 0
        if adx >= 25 and pdi > mdi:
            return "多头趋势增强"
        if adx >= 25 and mdi > pdi:
            return "空头趋势增强"
        if pdi > mdi:
            return "多头占优"
        if mdi > pdi:
            return "空头占优"
        return "趋势不明"

    def _indicator_matrix(
        self,
        trend: str,
        volume: str,
        macd: str,
        kdj: str,
        rsi: str,
        wr: str,
        psy: str,
        dmi: str,
        game: IntradayGame,
        chip_analysis: ChipAnalysis,
        latest_rsi: IndicatorPoint,
        latest_wr: IndicatorPoint,
        latest_psy: IndicatorPoint,
        latest_dmi: IndicatorPoint,
    ) -> list[IndicatorScore]:
        mappings = [
            ("趋势", "均线结构", trend, trend, {"强趋势": 16, "趋势修复": 9, "震荡": 0, "弱势": -14}),
            ("趋势", "DMI/ADX", dmi, f"+DI {latest_dmi.pdi:.1f} / -DI {latest_dmi.mdi:.1f} / ADX {latest_dmi.adx:.1f}", {"多头趋势增强": 13, "多头占优": 6, "趋势不明": 0, "空头占优": -7, "空头趋势增强": -14}),
            ("动量", "MACD", macd, macd, {"金叉偏多": 9, "钝化观察": 0, "死叉偏空": -9}),
            ("动量", "KDJ", kdj, kdj, {"短线偏多": 5, "低位超卖": 4, "短线偏弱": -5, "高位超买": -7}),
            ("动量", "RSI", rsi, f"{latest_rsi.value:.1f}", {"RSI偏强": 5, "RSI超卖": 3, "RSI中性": 0, "RSI偏弱": -4, "RSI过热": -5}),
            ("动量", "WR", wr, f"{latest_wr.value:.1f}", {"WR偏强": 3, "WR超卖": 3, "WR中性": 0, "WR偏弱": -3, "WR超买": -5}),
            ("量能", "成交量", volume, volume, {"温和放量": 7, "量能活跃": 5, "量能平稳": 0, "异常放量": -3, "缩量": -5}),
            ("量能", "分时博弈", game.status, f"多 {game.buy_power_pct:.1f}% / 空 {game.sell_power_pct:.1f}%", {"多方占优": 7, "均衡博弈": 0, "拉高回落": -6, "空方占优": -8}),
            ("位置", "PSY心理线", psy, f"{latest_psy.value:.1f}", {"情绪偏多": 4, "情绪冰点": 3, "情绪中性": 0, "情绪偏空": -3, "情绪过热": -6}),
            ("位置", "筹码盘", chip_analysis.status, chip_analysis.description, {"下方支撑占优": 7, "筹码均衡": 0, "上方压力偏重": -7, "筹码不足": 0}),
        ]
        return [
            IndicatorScore(group=group, name=name, status=status, value=value, contribution=score_map.get(status, 0))
            for group, name, status, value, score_map in mappings
        ]

    def _advice(
        self,
        matrix: list[IndicatorScore],
        volume: str,
        game: IntradayGame,
        chip_analysis: ChipAnalysis,
        close: float,
        support: float,
        resistance: float,
    ) -> DecisionAdvice:
        score = 50 + sum(item.contribution for item in matrix)
        reasons = [f"{item.name}{item.status}：{item.contribution:+d} 分" for item in matrix]
        warnings: list[str] = []
        if close > resistance * 0.97:
            warnings.append("价格接近 20 日压力区，追高需要等待放量确认。")
        if close < support * 1.03:
            reasons.append("靠近 20 日支撑区，适合观察承接。")
        if volume == "异常放量" and game.status != "多方占优":
            warnings.append("放量但分时多方不强，警惕冲高回落。")
        if chip_analysis.status == "上方压力偏重":
            warnings.append("现价上方筹码压力偏重，突破前不宜激进追高。")
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
