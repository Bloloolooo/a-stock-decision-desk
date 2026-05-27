from app.schemas import PositionCreate, PositionSell
from app.services.market_data import sample_market_data
import app.services.portfolio as portfolio_module
from app.services.portfolio import PortfolioService


def test_new_database_starts_with_empty_portfolio(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(portfolio_module, "market_data", sample_market_data)
    service = PortfolioService()

    assert service.positions() == []
    assert service.summary().cash == 0


def test_portfolio_persists_cash_and_position(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(portfolio_module, "market_data", sample_market_data)
    service = PortfolioService()
    service.set_cash(20000)
    service.upsert_position(
        PositionCreate(symbol="600519", name="贵州茅台", quantity=10, average_cost=1500)
    )

    fresh_service = PortfolioService()
    summary = fresh_service.summary()
    positions = {position.symbol: position for position in fresh_service.positions()}

    assert summary.cash == 5000
    assert positions["600519"].quantity == 10
    assert positions["600519"].average_cost == 1500


def test_portfolio_resolves_missing_name(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(portfolio_module, "market_data", sample_market_data)
    service = PortfolioService()
    service.set_cash(20000)
    position = service.upsert_position(
        PositionCreate(symbol="300308", quantity=100, average_cost=150)
    )

    assert position.name == "中际旭创"


def test_update_position_name_changes_label(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(portfolio_module, "market_data", sample_market_data)
    service = PortfolioService()
    service.set_cash(20000)
    service.upsert_position(PositionCreate(symbol="300308", quantity=100, average_cost=150))

    position = service.update_position_name("300308", "自定义标签")

    assert position.name == "自定义标签"
    assert service.positions()[0].name == "自定义标签"


def test_buy_position_appends_quantity_and_weighted_cost(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(portfolio_module, "market_data", sample_market_data)
    service = PortfolioService()
    service.set_cash(50000)
    service.upsert_position(PositionCreate(symbol="600519", quantity=10, average_cost=1000))
    position = service.upsert_position(PositionCreate(symbol="600519", quantity=10, average_cost=2000))
    summary = service.summary()

    assert position.quantity == 20
    assert position.average_cost == 1500
    assert summary.cash == 20000


def test_buy_position_rejects_when_cash_is_not_enough(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(portfolio_module, "market_data", sample_market_data)
    service = PortfolioService()
    service.set_cash(1000)

    try:
        service.upsert_position(PositionCreate(symbol="300308", quantity=100, average_cost=150))
    except ValueError as exc:
        assert "可用现金不足" in str(exc)
    else:
        raise AssertionError("Expected insufficient cash error")


def test_sell_position_reduces_quantity_and_adds_cash(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(portfolio_module, "market_data", sample_market_data)
    service = PortfolioService()
    service.set_cash(20000)
    service.upsert_position(PositionCreate(symbol="600519", quantity=10, average_cost=1500))

    service.sell_position(PositionSell(symbol="600519", quantity=4, sell_price=1800))
    positions = {position.symbol: position for position in service.positions()}
    summary = service.summary()

    assert positions["600519"].quantity == 6
    assert summary.cash == 12200


def test_trade_inputs_normalize_symbol_and_round_money(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(portfolio_module, "market_data", sample_market_data)
    service = PortfolioService()
    service.set_cash(1000.005)

    service.upsert_position(PositionCreate(symbol=" SZ300308 ", quantity=3, average_cost=10.005))
    service.sell_position(PositionSell(symbol="300308.SZ", quantity=1, sell_price=11.115))

    positions = {position.symbol: position for position in service.positions()}
    trades = service.trade_records()

    assert positions["300308"].quantity == 2
    assert positions["300308"].average_cost == 10.01
    assert service.summary().cash == 981.1
    assert [trade.symbol for trade in trades] == ["300308", "300308"]
    assert trades[0].price == 11.12
    assert trades[0].amount == 11.12


def test_sell_position_removes_last_shares(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(portfolio_module, "market_data", sample_market_data)
    service = PortfolioService()
    service.set_cash(20000)
    service.upsert_position(PositionCreate(symbol="300308", quantity=100, average_cost=150))

    service.sell_position(PositionSell(symbol="300308", quantity=100, sell_price=160))

    assert service.positions() == []
    assert service.summary().cash == 21000


def test_sell_position_rejects_when_quantity_is_too_large(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(portfolio_module, "market_data", sample_market_data)
    service = PortfolioService()
    service.set_cash(20000)
    service.upsert_position(PositionCreate(symbol="300308", quantity=100, average_cost=150))

    try:
        service.sell_position(PositionSell(symbol="300308", quantity=101, sell_price=160))
    except ValueError as exc:
        assert "卖出数量不能超过当前持仓" in str(exc)
    else:
        raise AssertionError("Expected oversell error")


def test_trade_records_include_buy_and_sell(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(portfolio_module, "market_data", sample_market_data)
    service = PortfolioService()
    service.set_cash(20000)
    service.upsert_position(
        PositionCreate(symbol="300308", quantity=100, average_cost=150)
    )
    service.sell_position(PositionSell(symbol="300308", quantity=40, sell_price=180))

    trades = service.trade_records()

    assert [trade.side for trade in trades] == ["sell", "buy"]
    assert trades[0].amount == 7200
