from datetime import date, datetime, timedelta

import app.services.screener as screener_module
from app.schemas import PriceBar
from app.services.screener import ScreenerService


class FakeMarketData:
    provider_name = "fake"
    description = "fake"
    last_source = "fake"
    last_error = None

    def __init__(self) -> None:
        self.series = {
            "000001": self._bars("000001", 10, 0.45),
            "000002": self._bars("000002", 22, -0.16, bounce=True),
            "000003": self._bars("000003", 8, 0.01, amount=5_000_000),
        }

    def latest_price(self, symbol: str) -> float:
        return self.series[symbol][-1].close

    def name(self, symbol: str) -> str:
        return {"000001": "趋势龙头", "000002": "超跌修复", "000003": "低流动"}.get(symbol, symbol)

    def bars(self, symbol: str, period: str = "daily", adjust: str = "qfq") -> list[PriceBar]:
        return self.series[symbol]

    def _bars(self, symbol: str, start: float, slope: float, amount: float = 100_000_000, bounce: bool = False) -> list[PriceBar]:
        today = date(2026, 5, 19)
        bars: list[PriceBar] = []
        for index in range(70):
            close = start + slope * index
            if bounce and index > 63:
                close += (index - 63) * 0.35
            close = max(close, 1.0)
            bars.append(
                PriceBar(
                    symbol=symbol,
                    period="daily",
                    trade_date=today - timedelta(days=69 - index),
                    timestamp=(today - timedelta(days=69 - index)).isoformat(),
                    open=close * 0.98,
                    high=close * 1.02,
                    low=close * 0.97,
                    close=close,
                    volume=1_000_000,
                    amount=amount,
                    updated_at=datetime.now(),
                )
            )
        return bars


def test_screener_scores_real_bars(monkeypatch) -> None:
    monkeypatch.setenv("SCREENER_SYMBOLS", "000001,000002,000003")
    monkeypatch.setattr(screener_module, "market_data", FakeMarketData())
    service = ScreenerService()

    trend = service.results("trend")
    rebound = service.results("rebound")

    assert trend[0].symbol == "000001"
    assert "5日" in trend[0].reason
    assert any(item["name"] == "均线结构" for item in trend[0].factors)
    assert rebound[0].symbol == "000002"
    assert "距20日高点" in rebound[0].reason
    assert any(item["name"] == "20日回撤" for item in rebound[0].factors)
    assert any(row.risk_status == "观察：流动性偏弱" for row in trend)


def test_screener_config_persists_and_invalid_symbols_are_ignored(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("SCREENER_SYMBOLS", "")
    service = ScreenerService()

    config = service.update_config([" 000001 ", "bad", "600519", "600519"])
    fresh_service = ScreenerService()

    assert config.symbols == ["000001", "600519"]
    assert fresh_service.config().symbols == ["000001", "600519"]
    assert fresh_service.status().pool_size == 2
