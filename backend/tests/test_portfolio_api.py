from fastapi import HTTPException

from app.schemas import CashUpdate, PositionCreate, PositionSell
from app.routers import portfolio as portfolio_router
from app.services.market_data import sample_market_data
import app.services.portfolio as portfolio_module
from app.services.portfolio import PortfolioService


def isolate_router(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STOCK_TOOL_DB_PATH", str(tmp_path / "api.sqlite3"))
    monkeypatch.setattr(portfolio_module, "market_data", sample_market_data)
    monkeypatch.setattr(portfolio_router, "portfolio_service", PortfolioService())


def test_portfolio_router_buy_sell_cash_flow(monkeypatch, tmp_path) -> None:
    isolate_router(monkeypatch, tmp_path)

    cash_response = portfolio_router.update_cash(CashUpdate(cash=50000.005))
    assert cash_response.cash == 50000.01

    first_buy = portfolio_router.upsert_position(PositionCreate(symbol=" SZ300308 ", quantity=100, average_cost=100.005))
    assert first_buy.symbol == "300308"
    assert first_buy.average_cost == 100.01

    second_buy = portfolio_router.upsert_position(PositionCreate(symbol="300308", quantity=100, average_cost=120))
    assert second_buy.quantity == 200
    assert second_buy.average_cost == 110.01

    sell_response = portfolio_router.sell_position(PositionSell(symbol="300308.SZ", quantity=50, sell_price=130.337))
    assert sell_response.cash == 34516.01

    positions = portfolio_router.get_positions()
    trades = portfolio_router.get_trade_records()

    assert positions[0].quantity == 150
    assert [trade.side for trade in trades] == ["sell", "buy", "buy"]
    assert trades[0].price == 130.34
    assert trades[0].amount == 6517.0


def test_portfolio_router_rejects_invalid_trade(monkeypatch, tmp_path) -> None:
    isolate_router(monkeypatch, tmp_path)

    portfolio_router.update_cash(CashUpdate(cash=1000))
    try:
        portfolio_router.upsert_position(PositionCreate(symbol="300308", quantity=100, average_cost=100))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "可用现金不足" in str(exc.detail)
    else:
        raise AssertionError("Expected insufficient cash error")

    portfolio_router.update_cash(CashUpdate(cash=20000))
    portfolio_router.upsert_position(PositionCreate(symbol="300308", quantity=100, average_cost=100))
    try:
        portfolio_router.sell_position(PositionSell(symbol="300308", quantity=101, sell_price=100))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "卖出数量不能超过当前持仓" in str(exc.detail)
    else:
        raise AssertionError("Expected oversell error")
