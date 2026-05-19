from datetime import datetime
from sqlite3 import Row

from app.db import get_connection, init_db
from app.schemas import PortfolioSummary, Position, PositionCreate, PositionSell
from app.services.market_data import market_data


class PortfolioService:
    def __init__(self) -> None:
        init_db()

    def set_cash(self, cash: float) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO account (id, cash, updated_at)
                VALUES (1, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET cash = excluded.cash, updated_at = excluded.updated_at
                """,
                (cash,),
            )

    def upsert_position(self, payload: PositionCreate) -> Position:
        normalized_payload = PositionCreate(
            **{
                **payload.model_dump(),
                "symbol": payload.symbol.strip(),
                "name": payload.name.strip() or market_data.name(payload.symbol.strip()),
            }
        )
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO positions (symbol, name, quantity, average_cost, note, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(symbol) DO UPDATE SET
                    name = excluded.name,
                    quantity = excluded.quantity,
                    average_cost = excluded.average_cost,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized_payload.symbol,
                    normalized_payload.name,
                    normalized_payload.quantity,
                    normalized_payload.average_cost,
                    normalized_payload.note,
                ),
            )
            connection.execute(
                """
                INSERT INTO trade_records (symbol, name, side, quantity, price, amount, note, created_at)
                VALUES (?, ?, 'buy', ?, ?, ?, ?, datetime('now'))
                """,
                (
                    normalized_payload.symbol,
                    normalized_payload.name,
                    normalized_payload.quantity,
                    normalized_payload.average_cost,
                    normalized_payload.quantity * normalized_payload.average_cost,
                    normalized_payload.note,
                ),
            )
        return self._position_view(normalized_payload)

    def sell_position(self, payload: PositionSell) -> None:
        symbol = payload.symbol.strip()
        with get_connection() as connection:
            row = connection.execute(
                "SELECT symbol, name, quantity, average_cost, note FROM positions WHERE symbol = ?",
                (symbol,),
            ).fetchone()
            if not row:
                raise ValueError(f"{symbol} 没有持仓")
            current_quantity = int(row["quantity"])
            if payload.quantity > current_quantity:
                raise ValueError(f"{symbol} 卖出数量不能超过当前持仓 {current_quantity}")

            remaining_quantity = current_quantity - payload.quantity
            if remaining_quantity == 0:
                connection.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
            else:
                connection.execute(
                    "UPDATE positions SET quantity = ?, updated_at = datetime('now') WHERE symbol = ?",
                    (remaining_quantity, symbol),
                )
            amount = payload.quantity * payload.sell_price
            connection.execute(
                """
                INSERT INTO account (id, cash, updated_at)
                VALUES (1, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET cash = cash + excluded.cash, updated_at = excluded.updated_at
                """,
                (amount,),
            )
            connection.execute(
                """
                INSERT INTO trade_records (symbol, name, side, quantity, price, amount, note, created_at)
                VALUES (?, ?, 'sell', ?, ?, ?, ?, datetime('now'))
                """,
                (symbol, row["name"], payload.quantity, payload.sell_price, amount, payload.note),
            )

    def positions(self) -> list[Position]:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT symbol, name, quantity, average_cost, note FROM positions ORDER BY updated_at DESC"
            ).fetchall()
        return [self._position_view(self._position_from_row(row)) for row in rows]

    def summary(self) -> PortfolioSummary:
        positions = self.positions()
        market_value = sum(position.market_value for position in positions)
        floating_pnl = sum(position.floating_pnl for position in positions)
        cash = self._cash()
        return PortfolioSummary(
            total_assets=round(cash + market_value, 2),
            cash=round(cash, 2),
            position_market_value=round(market_value, 2),
            floating_pnl=round(floating_pnl, 2),
            today_pnl=-1280.0,
            updated_at=datetime.now(),
        )

    def _cash(self) -> float:
        with get_connection() as connection:
            row = connection.execute("SELECT cash FROM account WHERE id = 1").fetchone()
        return float(row["cash"]) if row else 0.0

    def _position_from_row(self, row: Row) -> PositionCreate:
        return PositionCreate(
            symbol=row["symbol"],
            name=row["name"],
            quantity=int(row["quantity"]),
            average_cost=float(row["average_cost"]),
            note=row["note"],
        )

    def _position_view(self, payload: PositionCreate) -> Position:
        last_price = market_data.latest_price(payload.symbol)
        market_value = last_price * payload.quantity
        cost_value = payload.average_cost * payload.quantity
        floating_pnl = market_value - cost_value
        floating_pnl_pct = floating_pnl / cost_value if cost_value else 0
        return Position(
            **payload.model_dump(),
            last_price=round(last_price, 2),
            market_value=round(market_value, 2),
            floating_pnl=round(floating_pnl, 2),
            floating_pnl_pct=round(floating_pnl_pct, 4),
            updated_at=datetime.now(),
        )


portfolio_service = PortfolioService()
