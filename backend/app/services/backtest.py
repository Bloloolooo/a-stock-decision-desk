from datetime import date, datetime
import math
import statistics

from app.schemas import BacktestEquityPoint, BacktestRequest, BacktestResult, BacktestTrade, PriceBar
from app.services.market_data import market_data
from app.services.risk import fractional_kelly


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def atr(bars: list[PriceBar], window: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs: list[float] = []
    for index in range(1, len(bars)):
        current = bars[index]
        previous = bars[index - 1]
        trs.append(max(current.high - current.low, abs(current.high - previous.close), abs(current.low - previous.close)))
    return average(trs[-window:])


def signal_confidence(bars: list[PriceBar]) -> int:
    if len(bars) < 30:
        return 50
    closes = [bar.close for bar in bars]
    latest = bars[-1]
    ma5 = average(closes[-5:])
    ma10 = average(closes[-10:])
    ma20 = average(closes[-20:])
    ma60 = average(closes[-60:]) if len(closes) >= 60 else ma20
    volume_5 = average([bar.volume for bar in bars[-5:]])
    volume_20 = average([bar.volume for bar in bars[-20:]])
    volume_ratio = volume_5 / volume_20 if volume_20 else 1.0
    change_5 = latest.close / closes[-6] - 1 if len(closes) >= 6 and closes[-6] else 0.0
    change_20 = latest.close / closes[-21] - 1 if len(closes) >= 21 and closes[-21] else change_5
    score = 50
    score += 14 if latest.close > ma5 > ma20 > ma60 else 7 if latest.close > ma20 and ma5 > ma20 else -12 if latest.close < ma20 < ma60 else 0
    score += 8 if ma5 > ma10 > ma20 else 0
    score += min(12, max(-10, int(change_5 * 120)))
    score += min(10, max(-12, int(change_20 * 70)))
    score += min(8, max(-6, int((volume_ratio - 1) * 10)))
    return max(0, min(100, score))


class BacktestService:
    def run(self, payload: BacktestRequest) -> BacktestResult:
        symbol = "".join(ch for ch in payload.symbol.strip() if ch.isdigit())
        bars = [
            bar
            for bar in market_data.bars(symbol=symbol, period="daily")
            if (payload.start_date is None or bar.trade_date >= payload.start_date)
            and (payload.end_date is None or bar.trade_date <= payload.end_date)
        ]
        if len(bars) < 45:
            raise ValueError("回测样本不足，至少需要 45 个交易日。")

        cash = payload.initial_cash
        quantity = 0
        entry_price = 0.0
        entry_date: date | None = None
        highest_equity = payload.initial_cash
        cost_total = 0.0
        closed_returns: list[float] = []
        closed_pnls: list[float] = []
        holding_days: list[int] = []
        trades: list[BacktestTrade] = []
        equity_curve: list[BacktestEquityPoint] = []
        daily_returns: list[float] = []
        previous_equity = payload.initial_cash

        for index, bar in enumerate(bars):
            history = bars[: index + 1]
            confidence = signal_confidence(history)
            current_atr = atr(history)
            stop_loss_price = entry_price - current_atr * payload.atr_multiplier if quantity else 0.0

            if quantity > 0 and (confidence <= payload.sell_threshold or bar.close <= stop_loss_price):
                sell_price = bar.close * (1 - payload.slippage_rate)
                amount = sell_price * quantity
                fee = amount * (payload.commission_rate + payload.stamp_tax_rate)
                pnl = amount - fee - entry_price * quantity
                pnl_pct = pnl / (entry_price * quantity) if entry_price else 0.0
                cash += amount - fee
                cost_total += fee
                closed_pnls.append(pnl)
                closed_returns.append(pnl_pct)
                if entry_date:
                    holding_days.append((bar.trade_date - entry_date).days)
                trades.append(
                    BacktestTrade(
                        trade_date=bar.trade_date,
                        side="sell",
                        price=round(sell_price, 2),
                        quantity=quantity,
                        amount=round(amount, 2),
                        fee=round(fee, 2),
                        reason="ATR止损" if bar.close <= stop_loss_price else "信号转弱",
                        confidence=confidence,
                        pnl=round(pnl, 2),
                        pnl_pct=round(pnl_pct * 100, 2),
                    )
                )
                quantity = 0
                entry_price = 0.0
                entry_date = None

            if quantity == 0 and confidence >= payload.buy_threshold:
                buy_price = bar.close * (1 + payload.slippage_rate)
                budget = min(cash, payload.initial_cash * payload.max_position_ratio)
                buy_quantity = int(budget // (buy_price * 100)) * 100
                if buy_quantity > 0:
                    amount = buy_price * buy_quantity
                    fee = amount * payload.commission_rate
                    if amount + fee <= cash:
                        cash -= amount + fee
                        cost_total += fee
                        quantity = buy_quantity
                        entry_price = buy_price
                        entry_date = bar.trade_date
                        trades.append(
                            BacktestTrade(
                                trade_date=bar.trade_date,
                                side="buy",
                                price=round(buy_price, 2),
                                quantity=buy_quantity,
                                amount=round(amount, 2),
                                fee=round(fee, 2),
                                reason="信号达标",
                                confidence=confidence,
                            )
                        )

            equity = cash + quantity * bar.close
            highest_equity = max(highest_equity, equity)
            drawdown = equity / highest_equity - 1 if highest_equity else 0.0
            daily_returns.append(equity / previous_equity - 1 if previous_equity else 0.0)
            previous_equity = equity
            equity_curve.append(
                BacktestEquityPoint(
                    trade_date=bar.trade_date,
                    equity=round(equity, 2),
                    cash=round(cash, 2),
                    position_value=round(quantity * bar.close, 2),
                    drawdown_pct=round(drawdown * 100, 2),
                    confidence=confidence,
                )
            )

        final_equity = equity_curve[-1].equity
        days = max(1, (bars[-1].trade_date - bars[0].trade_date).days)
        total_return = final_equity / payload.initial_cash - 1
        annual_return = (1 + total_return) ** (365 / days) - 1 if total_return > -1 else -1
        downside = min(point.drawdown_pct for point in equity_curve)
        wins = [value for value in closed_pnls if value > 0]
        losses = [abs(value) for value in closed_pnls if value < 0]
        win_rate = len(wins) / len(closed_pnls) if closed_pnls else 0.0
        win_loss_ratio = average(wins) / average(losses) if wins and losses else 0.0
        volatility = statistics.pstdev(daily_returns) if len(daily_returns) > 1 else 0.0
        sharpe = average(daily_returns) / volatility * math.sqrt(252) if volatility else 0.0
        kelly = fractional_kelly(win_rate=win_rate, win_loss_ratio=win_loss_ratio, fraction=0.25)
        summary = (
            f"扣费后收益 {total_return * 100:+.2f}%，最大回撤 {downside:.2f}%，"
            f"胜率 {win_rate * 100:.1f}%，盈亏比 {win_loss_ratio:.2f}。"
        )
        return BacktestResult(
            symbol=symbol,
            name=market_data.name(symbol),
            start_date=bars[0].trade_date,
            end_date=bars[-1].trade_date,
            initial_cash=round(payload.initial_cash, 2),
            final_equity=round(final_equity, 2),
            total_return_pct=round(total_return * 100, 2),
            annual_return_pct=round(annual_return * 100, 2),
            max_drawdown_pct=round(downside, 2),
            sharpe_ratio=round(sharpe, 2),
            win_rate=round(win_rate, 4),
            win_loss_ratio=round(win_loss_ratio, 4),
            trade_count=len(trades),
            average_holding_days=round(average(holding_days), 1),
            estimated_kelly_ratio=round(kelly, 4),
            cost_total=round(cost_total, 2),
            trades=trades[-80:],
            equity_curve=equity_curve[-240:],
            summary=summary,
        )


backtest_service = BacktestService()
