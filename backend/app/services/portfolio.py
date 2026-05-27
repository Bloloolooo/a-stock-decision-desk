from datetime import datetime
from sqlite3 import Connection, Row

from app.db import get_connection, init_db
from app.schemas import PortfolioSummary, Position, PositionCreate, PositionSell, TradeRecord, WatchItem, WatchItemCreate
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
                (_money(cash),),
            )

    def upsert_position(self, payload: PositionCreate) -> Position:
        symbol = _normalize_symbol(payload.symbol)
        normalized_payload = PositionCreate(
            **{
                **payload.model_dump(),
                "symbol": symbol,
                "name": payload.name.strip() or market_data.name(symbol),
                "average_cost": _money(payload.average_cost),
            }
        )
        buy_amount = _money(normalized_payload.quantity * normalized_payload.average_cost)
        with get_connection() as connection:
            self._ensure_account(connection)
            cash = self._cash(connection)
            if buy_amount > cash + 0.005:
                raise ValueError(f"可用现金不足，买入需 {buy_amount:.2f}，当前现金 {cash:.2f}")
            row = connection.execute(
                "SELECT symbol, name, quantity, average_cost, note FROM positions WHERE symbol = ?",
                (normalized_payload.symbol,),
            ).fetchone()
            if row:
                current_quantity = int(row["quantity"])
                new_quantity = current_quantity + normalized_payload.quantity
                cost_value = current_quantity * float(row["average_cost"]) + buy_amount
                average_cost = _money(cost_value / new_quantity) if new_quantity else normalized_payload.average_cost
                name = row["name"] or normalized_payload.name
                note = normalized_payload.note or row["note"]
            else:
                new_quantity = normalized_payload.quantity
                average_cost = normalized_payload.average_cost
                name = normalized_payload.name
                note = normalized_payload.note
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
                    name,
                    new_quantity,
                    average_cost,
                    note,
                ),
            )
            connection.execute(
                """
                UPDATE account
                SET cash = ROUND(cash - ?, 2), updated_at = datetime('now')
                WHERE id = 1
                """,
                (buy_amount,),
            )
            connection.execute(
                """
                INSERT INTO trade_records (symbol, name, side, quantity, price, amount, note, created_at)
                VALUES (?, ?, 'buy', ?, ?, ?, ?, datetime('now'))
                """,
                (
                    normalized_payload.symbol,
                    name,
                    normalized_payload.quantity,
                    normalized_payload.average_cost,
                    buy_amount,
                    normalized_payload.note,
                ),
            )
        return self._position_view(
            PositionCreate(
                symbol=normalized_payload.symbol,
                name=name,
                quantity=new_quantity,
                average_cost=average_cost,
                note=note,
            )
        )

    def sell_position(self, payload: PositionSell) -> None:
        symbol = _normalize_symbol(payload.symbol)
        sell_price = _money(payload.sell_price)
        with get_connection() as connection:
            self._ensure_account(connection)
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
            amount = _money(payload.quantity * sell_price)
            connection.execute(
                """
                UPDATE account
                SET cash = ROUND(cash + ?, 2), updated_at = datetime('now')
                WHERE id = 1
                """,
                (amount,),
            )
            connection.execute(
                """
                INSERT INTO trade_records (symbol, name, side, quantity, price, amount, note, created_at)
                VALUES (?, ?, 'sell', ?, ?, ?, ?, datetime('now'))
                """,
                (symbol, row["name"], payload.quantity, sell_price, amount, payload.note),
            )

    def update_position_name(self, symbol: str, name: str) -> Position:
        normalized_symbol = _normalize_symbol(symbol)
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("名称不能为空")
        with get_connection() as connection:
            row = connection.execute(
                "SELECT symbol, name, quantity, average_cost, note FROM positions WHERE symbol = ?",
                (normalized_symbol,),
            ).fetchone()
            if not row:
                raise ValueError(f"{normalized_symbol} 没有持仓")
            connection.execute(
                "UPDATE positions SET name = ?, updated_at = datetime('now') WHERE symbol = ?",
                (normalized_name, normalized_symbol),
            )
            updated = PositionCreate(
                symbol=row["symbol"],
                name=normalized_name,
                quantity=int(row["quantity"]),
                average_cost=float(row["average_cost"]),
                note=row["note"],
            )
        return self._position_view(updated)

    def add_watch_item(self, payload: WatchItemCreate) -> WatchItem:
        symbol = _normalize_symbol(payload.symbol)
        name = payload.name.strip() or market_data.name(symbol)
        tags = payload.tags.strip()
        note = payload.note.strip()
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO watchlist (symbol, name, tags, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(symbol) DO UPDATE SET
                    name = excluded.name,
                    tags = excluded.tags,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (symbol, name, tags, note),
            )
        return self._watch_item_view(WatchItemCreate(symbol=symbol, name=name, tags=tags, note=note))

    def watchlist(self) -> list[WatchItem]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT symbol, name, tags, note, created_at, updated_at
                FROM watchlist
                ORDER BY datetime(updated_at) DESC, symbol
                """
            ).fetchall()
        return [
            WatchItem(
                symbol=row["symbol"],
                name=row["name"],
                tags=row["tags"],
                note=row["note"],
                last_price=round(market_data.latest_price(row["symbol"]), 2),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        ]

    def delete_watch_item(self, symbol: str) -> None:
        normalized_symbol = _normalize_symbol(symbol)
        with get_connection() as connection:
            connection.execute("DELETE FROM watchlist WHERE symbol = ?", (normalized_symbol,))

    def positions(self) -> list[Position]:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT symbol, name, quantity, average_cost, note FROM positions ORDER BY updated_at DESC"
            ).fetchall()
        return [self._position_view(self._position_from_row(row)) for row in rows]

    def trade_records(self, limit: int = 100) -> list[TradeRecord]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, symbol, name, side, quantity, price, amount, note, created_at
                FROM trade_records
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            TradeRecord(
                id=int(row["id"]),
                symbol=row["symbol"],
                name=row["name"],
                side=row["side"],
                quantity=int(row["quantity"]),
                price=round(float(row["price"]), 2),
                amount=round(float(row["amount"]), 2),
                note=row["note"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

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

    def _cash(self, connection: Connection | None = None) -> float:
        if connection is not None:
            row = connection.execute("SELECT cash FROM account WHERE id = 1").fetchone()
            return float(row["cash"]) if row else 0.0
        with get_connection() as connection:
            row = connection.execute("SELECT cash FROM account WHERE id = 1").fetchone()
        return float(row["cash"]) if row else 0.0

    def _ensure_account(self, connection: Connection) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO account (id, cash, updated_at)
            VALUES (1, 0.0, datetime('now'))
            """
        )

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

    def _watch_item_view(self, payload: WatchItemCreate) -> WatchItem:
        now = datetime.now()
        return WatchItem(
            symbol=payload.symbol,
            name=payload.name,
            tags=payload.tags,
            note=payload.note,
            last_price=round(market_data.latest_price(payload.symbol), 2),
            created_at=now,
            updated_at=now,
        )


portfolio_service = PortfolioService()


def _normalize_symbol(symbol: str) -> str:
    normalized = "".join(character for character in symbol.strip() if character.isdigit())
    if len(normalized) != 6:
        raise ValueError("请输入 6 位股票代码")
    return normalized


def _money(value: float) -> float:
    return round(float(value) + 1e-9, 2)
