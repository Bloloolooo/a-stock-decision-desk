from app.services.market_data import MarketDataManager


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
