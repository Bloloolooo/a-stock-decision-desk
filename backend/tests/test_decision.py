from datetime import date, datetime, timedelta

import app.services.decision as decision_module
from app.schemas import PriceBar
from app.services.decision import DecisionService


class FakeMarketData:
    provider_name = "fake"
    description = "fake"
    last_source = "fake"
    last_error = None

    def name(self, symbol: str) -> str:
        return "测试股票"

    def latest_price(self, symbol: str) -> float:
        return self.bars(symbol)[-1].close

    def bars(self, symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
        count = 90 if period == "daily" else 80
        today = date(2026, 5, 26)
        bars: list[PriceBar] = []
        for index in range(count):
            close = 10 + index * 0.12
            volume = 1_000_000 + index * 12_000
            trade_date = today - timedelta(days=count - index)
            timestamp = trade_date.isoformat() if period == "daily" else f"{trade_date.isoformat()} 10:{index % 60:02d}:00"
            bars.append(
                PriceBar(
                    symbol=symbol,
                    period=period,
                    trade_date=trade_date,
                    timestamp=timestamp,
                    open=close * 0.99,
                    high=close * 1.02,
                    low=close * 0.98,
                    close=close,
                    volume=volume,
                    amount=volume * close,
                    turnover_rate=2.5,
                    updated_at=datetime.now(),
                )
            )
        return bars


def test_decision_center_calculates_core_indicators(monkeypatch) -> None:
    monkeypatch.setattr(decision_module, "market_data", FakeMarketData())
    result = DecisionService().decision("000001")

    assert result.symbol == "000001"
    assert result.trend_status == "强趋势"
    assert result.volume_ratio > 0
    assert len(result.macd) > 0
    assert len(result.kdj) > 0
    assert len(result.chips) > 0
    assert result.market_regime in {"多头趋势", "空头趋势", "震荡", "高波动", "趋势过渡"}
    assert result.trading_plan.buy_breakout_price > result.current_price
    assert result.trading_plan.take_profit_2 > result.trading_plan.take_profit_1
    assert result.trading_plan.risk_reward_ratio > 0
    assert result.advice.action in {"可买/可加仓", "持有观察", "观望", "减仓/规避"}
