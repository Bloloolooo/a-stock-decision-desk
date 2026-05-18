from app.schemas import PositionCreate
from app.services.market_data import sample_market_data
import app.services.portfolio as portfolio_module
from app.services.portfolio import PortfolioService


def test_portfolio_persists_cash_and_position(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(portfolio_module, "market_data", sample_market_data)
    service = PortfolioService()
    service.set_cash(12345)
    service.upsert_position(
        PositionCreate(symbol="600519", name="贵州茅台", quantity=10, average_cost=1500)
    )

    fresh_service = PortfolioService()
    summary = fresh_service.summary()
    positions = {position.symbol: position for position in fresh_service.positions()}

    assert summary.cash == 12345
    assert positions["600519"].quantity == 10
    assert positions["600519"].average_cost == 1500


def test_portfolio_resolves_missing_name(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(portfolio_module, "market_data", sample_market_data)
    service = PortfolioService()
    position = service.upsert_position(
        PositionCreate(symbol="300308", quantity=100, average_cost=150)
    )

    assert position.name == "中际旭创"
