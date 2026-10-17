"""SQLite store implementation satisfying Store protocol (Role C).

Persists signals, risk decisions, trades, and periodic equity curve snapshots.
"""
import sqlite3
import logging
from typing import List, Dict, Any
from app.models import Signal, RiskDecision, OrderRequest, OrderResult
from app.interfaces import Store
from app.config import settings

logger = logging.getLogger("app.storage.store")

class SQLiteStore(Store):
    """SQLite implementation for trade logs and telemetry."""
    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Create database tables if they do not exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    side TEXT,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    reason TEXT,
                    approved INTEGER,
                    approved_size REAL,
                    ts INTEGER
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    side TEXT,
                    size REAL,
                    entry_price REAL,
                    client_order_id TEXT,
                    order_id TEXT,
                    status TEXT,
                    error TEXT,
                    ts INTEGER
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS equity_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER,
                    equity REAL
                )
            """)

    def save_signal(self, signal: Signal, decision: RiskDecision) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO signals (symbol, side, entry_price, stop_loss, take_profit, reason, approved, approved_size, ts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (signal.symbol, signal.side, signal.entry_price, signal.stop_loss, signal.take_profit, signal.reason,
                 1 if decision.approved else 0, decision.size, signal.ts)
            )

    def save_trade(self, order: OrderRequest, result: OrderResult) -> None:
        import time
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO trades (symbol, side, size, entry_price, client_order_id, order_id, status, error, ts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (order.symbol, order.side, order.size, order.entry_price, order.client_order_id,
                 result.order_id, result.status, result.error, int(time.time()))
            )

    def save_equity(self, ts: int, equity: float) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO equity_snapshots (ts, equity) VALUES (?, ?)",
                (ts, equity)
            )

    def get_trades(self, limit: int = 100) -> List[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_equity_curve(self, limit: int = 1000) -> List[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM equity_snapshots ORDER BY ts ASC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]
