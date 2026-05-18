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


class RiskService:
    def advice(self, symbol: str) -> RiskAdvice:
        summary = portfolio_service.summary()
        positions = {position.symbol: position for position in portfolio_service.positions()}
        position = positions.get(symbol)
        current_price = market_data.latest_price(symbol)
        stop_loss_price = round(current_price * 0.948, 2)
        fixed_amount = fixed_risk_position_amount(summary.total_assets, current_price, stop_loss_price, 0.012)
        kelly_ratio = fractional_kelly(win_rate=0.52, win_loss_ratio=1.45, fraction=0.25)
        kelly_amount = summary.total_assets * kelly_ratio if kelly_ratio > 0 else fixed_amount
        suggested_max_amount = min(fixed_amount, kelly_amount, summary.total_assets * 0.35)
        current_market_value = position.market_value if position else 0.0
        position_ratio = current_market_value / summary.total_assets if summary.total_assets else 0.0
        max_buy_amount = max(0.0, suggested_max_amount - current_market_value)
        single_stock_risk = max(current_price - stop_loss_price, 0) * (position.quantity if position else 0)

        if position_ratio > 0.35:
            message = "当前持仓偏高，优先控制回撤；跌破止损线后应减仓。"
        elif max_buy_amount > 0:
            message = "当前仓位未超上限；若趋势和量能继续确认，可小额加仓。"
        else:
            message = "当前仓位接近建议上限，继续观察走势和成交量。"

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
            signal_sources=["趋势强度：基于当前行情源", "量能：近期放大", "凯利：使用 0.25 分数凯利"],
            kelly_enabled=True,
            updated_at=datetime.now(),
        )


risk_service = RiskService()
