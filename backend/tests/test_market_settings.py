from datetime import date, datetime

import pytest

from app.schemas import PriceBar
from app.services.market_data import (
    AkShareMarketDataProvider,
    BaoStockMarketDataProvider,
    EfinanceMarketDataProvider,
    MarketDataManager,
    TushareMarketDataProvider,
)


def test_market_settings_persist_provider_and_token(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    manager = MarketDataManager()

    settings = manager.update_settings(provider="tushare", tushare_token="token-123")
    fresh = MarketDataManager()

    assert settings.provider == "tushare"
    assert settings.tushare_token_configured is True
    assert fresh.settings().provider == "tushare"
    assert fresh.settings().tushare_token_configured is True


def test_market_settings_reject_unknown_provider(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    manager = MarketDataManager()

    settings = manager.update_settings(provider="unknown")

    assert settings.provider == "auto"


def test_market_settings_accepts_extra_free_providers(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    manager = MarketDataManager()

    for provider in ["efinance", "baostock", "tencent"]:
        settings = manager.update_settings(provider=provider)
        assert settings.provider == provider


def test_auto_provider_uses_safe_source_by_default(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ENABLE_AKSHARE", raising=False)
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    manager = MarketDataManager()

    assert manager._provider().provider_name == "tencent"


def test_explicit_akshare_falls_back_when_not_enabled(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ENABLE_AKSHARE", raising=False)
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    manager = MarketDataManager()

    manager.update_settings(provider="akshare")

    assert manager.settings().provider == "akshare"
    assert manager._provider().provider_name == "tencent"


@pytest.mark.parametrize(
    "provider",
    [
        EfinanceMarketDataProvider(),
        BaoStockMarketDataProvider(),
        TushareMarketDataProvider(token="token"),
    ],
)
def test_non_akshare_providers_do_not_fallback_to_akshare_for_intraday(monkeypatch, provider) -> None:
    def fail_akshare_bars(self, *args, **kwargs):
        raise AssertionError("AkShare bars should not be called")

    def fake_sina_bars(self, symbol: str, period: str, adjust: str) -> list[PriceBar]:
        return [
            PriceBar(
                symbol=symbol,
                period=period,
                trade_date=date(2026, 5, 28),
                timestamp="2026-05-28 09:31:00",
                open=10.0,
                high=10.2,
                low=9.9,
                close=10.1,
                volume=1000,
                amount=10100,
                turnover_rate=None,
                adjust=adjust,
                updated_at=datetime(2026, 5, 28, 9, 31),
            )
        ]

    monkeypatch.setattr(AkShareMarketDataProvider, "bars", fail_akshare_bars)
    monkeypatch.setattr(AkShareMarketDataProvider, "_fetch_sina_bars", fake_sina_bars)

    bars = provider.bars(symbol="300308", period="intraday")

    assert bars[0].symbol == "300308"
    assert provider.last_source == "sina"
