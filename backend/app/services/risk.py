from datetime import datetime

from app.schemas import RiskAdvice
from app.services.market_data import market_data
from app.services.portfolio import portfolio_service


def fixed_risk_position_amount(total_assets: float, current_price: float, stop_loss_price: float, risk_ratio: float) -> float:
    per_share_risk = max(current_price - stop_loss_price, 0.01)
    shares = (total_assets * risk_ratio) / per_share_risk
    return shares * current_price


def fractional_kelly(win_rate: float, win_loss_ratio: float, fraction: float = 0.25) -> float:
    if win_rate <= 0 or win_rate >= 1 or win_loss_ratio <= 0:
        return 0.0
    raw = win_rate - ((1 - win_rate) / win_loss_ratio)
    return max(0.0, raw * fraction)


def average_true_range(bars, window: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    ranges = []
    for index in range(1, len(bars)):
        current = bars[index]
        previous = bars[index - 1]
        ranges.append(max(current.high - current.low, abs(current.high - previous.close), abs(current.low - previous.close)))
    scoped = ranges[-window:]
    return sum(scoped) / len(scoped) if scoped else 0.0


def trading_edge_from_records() -> tuple[float, float, str]:
    records = list(reversed(portfolio_service.trade_records(limit=300)))
    lots: dict[str, list[tuple[int, float]]] = {}
    realized: list[float] = []
    for trade in records:
        if trade.side == "buy":
            lots.setdefault(trade.symbol, []).append((trade.quantity, trade.price))
            continue
        remaining = trade.quantity
        symbol_lots = lots.setdefault(trade.symbol, [])
        while remaining > 0 and symbol_lots:
            quantity, price = symbol_lots[0]
            matched = min(quantity, remaining)
            realized.append((trade.price - price) * matched)
            remaining -= matched
            if matched == quantity:
                symbol_lots.pop(0)
            else:
                symbol_lots[0] = (quantity - matched, price)
    if len(realized) < 3:
        return 0.52, 1.45, "样本不足，暂用默认胜率 52%、盈亏比 1.45"
    wins = [value for value in realized if value > 0]
    losses = [abs(value) for value in realized if value < 0]
    if not wins or not losses:
        return 0.52, 1.45, "真实交易样本单边，暂用默认胜率 52%、盈亏比 1.45"
    win_rate = len(wins) / len(realized)
    win_loss_ratio = (sum(wins) / len(wins)) / (sum(losses) / len(losses))
    return win_rate, win_loss_ratio, f"基于 {len(realized)} 笔已平仓交易估算胜率/盈亏比"


class RiskService:
    def advice(self, symbol: str) -> RiskAdvice:
        summary = portfolio_service.summary()
        positions = {position.symbol: position for position in portfolio_service.positions()}
        position = positions.get(symbol)
        current_price = market_data.latest_price(symbol)
        daily = market_data.bars(symbol=symbol, period="daily")
        atr = average_true_range(daily[-60:])
        stop_loss_distance = max(atr * 2, current_price * 0.03)
        stop_loss_price = round(max(0.01, current_price - stop_loss_distance), 2)
        fixed_amount = fixed_risk_position_amount(summary.total_assets, current_price, stop_loss_price, 0.012)
        win_rate, win_loss_ratio, kelly_source = trading_edge_from_records()
        kelly_ratio = fractional_kelly(win_rate=win_rate, win_loss_ratio=win_loss_ratio, fraction=0.25)
        kelly_amount = summary.total_assets * kelly_ratio if kelly_ratio > 0 else fixed_amount
        suggested_max_amount = min(fixed_amount, kelly_amount, summary.total_assets * 0.35)
        current_market_value = position.market_value if position else 0.0
        position_ratio = current_market_value / summary.total_assets if summary.total_assets else 0.0
        max_buy_amount = max(0.0, suggested_max_amount - current_market_value)
        single_stock_risk = max(current_price - stop_loss_price, 0) * (position.quantity if position else 0)
        stop_loss_gap = (current_price - stop_loss_price) / current_price if current_price else 0
        cash_ratio = summary.cash / summary.total_assets if summary.total_assets else 0

        if position_ratio > 0.35:
            message = "当前单票仓位已经高于建议上沿，先守纪律，新增资金不要再追。"
            action_suggestions = [
                f"若跌破 {stop_loss_price:.2f}，先卖出 1/3 到 1/2，避免单票回撤扩大。",
                "若继续放量上攻，只做移动止盈，不再主动加仓。",
                f"把单票仓位降回 {(0.35 * 100):.0f}% 以内后，再考虑下一笔交易。",
            ]
        elif max_buy_amount > 0:
            message = "当前仓位仍有余量，但只适合分批，不适合一次打满。"
            action_suggestions = [
                f"单次加仓不超过 {round(max_buy_amount / 2, 2)} 元，留一半额度等回踩确认。",
                f"价格接近 {stop_loss_price:.2f} 且无量能修复时，不做补仓摊平。",
                "若收盘仍站稳短期均线，再把它纳入下一次加仓候选。",
            ]
        else:
            message = "当前仓位接近模型上限，下一步重点是持仓管理，不是扩大风险。"
            action_suggestions = [
                "保持观察，等待放量突破或回踩不破后再更新计划。",
                f"跌破 {stop_loss_price:.2f} 先执行减仓，盈利票可以用移动止盈替代固定止损。",
                "没有新增胜率信息时，不提高仓位上限。",
            ]

        return RiskAdvice(
            symbol=symbol,
            name=market_data.name(symbol),
            current_price=round(current_price, 2),
            position_ratio=round(position_ratio, 4),
            suggested_min_ratio=0.25,
            suggested_max_ratio=0.35,
            max_buy_amount=round(max_buy_amount, 2),
            stop_loss_price=stop_loss_price,
            single_stock_risk=round(single_stock_risk, 2),
            message=message,
            signal_sources=[
                f"仓位：当前单票约 {position_ratio * 100:.1f}%，建议区间 25%-35%",
                f"风控：ATR约 {atr:.2f}，止损距离约 {stop_loss_gap * 100:.1f}%，单票风险 {round(single_stock_risk, 2)} 元",
                f"资金：现金占比约 {cash_ratio * 100:.1f}%，最大可加仓 {round(max_buy_amount, 2)} 元",
                f"凯利：{kelly_source}，当前使用 {kelly_ratio * 100:.1f}% 分数凯利上限",
            ],
            action_suggestions=action_suggestions,
            kelly_enabled=True,
            updated_at=datetime.now(),
        )


risk_service = RiskService()
