from datetime import date, datetime, timedelta

import app.services.backtest as backtest_module
from app.schemas import BacktestRequest, PriceBar
from app.services.backtest import BacktestService


class FakeMarketData:
    def name(self, symbol: str) -> str:
        return "回测股票"

    def bars(self, symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
        today = date(2026, 5, 26)
        bars: list[PriceBar] = []
        for index in range(120):
            wave = (index % 18) * 0.03
            close = 10 + index * 0.05 + wave
            if 65 <= index <= 78:
                close -= (index - 64) * 0.18
            trade_date = today - timedelta(days=120 - index)
            bars.append(
                PriceBar(
                    symbol=symbol,
                    period=period,
                    trade_date=trade_date,
                    timestamp=trade_date.isoformat(),
                    open=close * 0.99,
                    high=close * 1.02,
                    low=close * 0.98,
                    close=close,
                    volume=1_000_000 + index * 10_000,
                    amount=(1_000_000 + index * 10_000) * close,
                    updated_at=datetime.now(),
                )
            )
        return bars


def test_backtest_runs_with_costs_and_metrics(monkeypatch) -> None:
    monkeypatch.setattr(backtest_module, "market_data", FakeMarketData())

    result = BacktestService().run(BacktestRequest(symbol="000001", buy_threshold=64, sell_threshold=52))

    assert result.symbol == "000001"
    assert result.trade_count > 0
    assert result.cost_total > 0
    assert result.start_date < result.end_date
    assert len(result.equity_curve) > 0
    assert "扣费后收益" in result.summary


def test_backtest_rejects_short_history(monkeypatch) -> None:
    class ShortMarketData(FakeMarketData):
        def bars(self, symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
            return super().bars(symbol, period, adjust)[:20]

    monkeypatch.setattr(backtest_module, "market_data", ShortMarketData())

    try:
        BacktestService().run(BacktestRequest(symbol="000001"))
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected short history failure")

    assert "样本不足" in message
