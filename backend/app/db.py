from pathlib import Path
import sqlite3
import os

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "stock_tool.sqlite3"


def db_path() -> Path:
    configured_path = os.getenv("STOCK_TOOL_DB_PATH")
    return Path(configured_path) if configured_path else DEFAULT_DB_PATH


def get_connection() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS account (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                cash REAL NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity >= 0),
                average_cost REAL NOT NULL CHECK (average_cost > 0),
                note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO account (id, cash, updated_at)
            VALUES (1, 92180.0, datetime('now'))
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO positions (symbol, name, quantity, average_cost, note, updated_at)
            VALUES
                ('300308', '中际旭创', 600, 151.55, '', datetime('now')),
                ('300750', '宁德时代', 300, 205.44, '', datetime('now'))
            """
        )
