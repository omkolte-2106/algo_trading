"""Database storage implementation satisfying Store protocol (Role C).

Provides PostgreSQL persistence with automatic table initialization,
connection management, and query helpers for signals, trades, equity, and risk events.
Includes SQLiteStore as a fallback.
"""
import logging
import time
import sqlite3
from typing import List, Dict, Any, Optional

from app.models import Signal, RiskDecision, OrderRequest, OrderResult
from app.interfaces import Store
from app.config import settings

logger = logging.getLogger("app.storage.store")

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


class PostgresStore(Store):
    """PostgreSQL implementation of the Store protocol."""

    def __init__(
        self,
        dbname: str = settings.DB_NAME,
        user: str = settings.DB_USER,
        password: str = settings.DB_PASSWORD,
        host: str = settings.DB_HOST,
        port: int = settings.DB_PORT,
    ):
        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2 is required for PostgresStore. Run: pip install psycopg2-binary")

        self.conn_params = {
            "dbname": dbname,
            "user": user,
            "password": password,
            "host": host,
            "port": port,
        }
        self._init_db()

    def _get_connection(self):
        """Create a new database connection."""
        return psycopg2.connect(**self.conn_params)

    def _init_db(self) -> None:
        """Create required tables and indexes if they do not exist."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS signals (
                        id SERIAL PRIMARY KEY,
                        symbol VARCHAR(32) NOT NULL,
                        side VARCHAR(16) NOT NULL,
                        entry_price DOUBLE PRECISION NOT NULL,
                        stop_loss DOUBLE PRECISION NOT NULL,
                        take_profit DOUBLE PRECISION NOT NULL,
                        reason TEXT,
                        approved BOOLEAN NOT NULL,
                        approved_size DOUBLE PRECISION NOT NULL,
                        ts BIGINT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts DESC);

                    CREATE TABLE IF NOT EXISTS trades (
                        id SERIAL PRIMARY KEY,
                        symbol VARCHAR(32) NOT NULL,
                        side VARCHAR(16) NOT NULL,
                        size DOUBLE PRECISION NOT NULL,
                        entry_price DOUBLE PRECISION NOT NULL,
                        client_order_id VARCHAR(128),
                        order_id VARCHAR(128),
                        status VARCHAR(64),
                        error TEXT,
                        ts BIGINT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_trades_ts ON trades(ts DESC);

                    CREATE TABLE IF NOT EXISTS equity_snapshots (
                        id SERIAL PRIMARY KEY,
                        ts BIGINT NOT NULL,
                        equity DOUBLE PRECISION NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_equity_ts ON equity_snapshots(ts ASC);

                    CREATE TABLE IF NOT EXISTS risk_events (
                        id SERIAL PRIMARY KEY,
                        event_type VARCHAR(64) NOT NULL,
                        reason TEXT NOT NULL,
                        ts BIGINT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_risk_events_ts ON risk_events(ts DESC);
                """)
            conn.commit()
        logger.info(f"[storage] Connected to PostgreSQL database '{self.conn_params['dbname']}' and initialized tables.")

    def save_signal(self, signal: Signal, decision: RiskDecision) -> None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO signals (symbol, side, entry_price, stop_loss, take_profit, reason, approved, approved_size, ts)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        signal.symbol,
                        signal.side,
                        float(signal.entry_price),
                        float(signal.stop_loss),
                        float(signal.take_profit),
                        signal.reason,
                        bool(decision.approved),
                        float(decision.size),
                        int(signal.ts),
                    ),
                )
            conn.commit()

    def save_trade(self, order: OrderRequest, result: OrderResult) -> None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trades (symbol, side, size, entry_price, client_order_id, order_id, status, error, ts)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        order.symbol,
                        order.side,
                        float(order.size),
                        float(order.entry_price),
                        order.client_order_id,
                        result.order_id,
                        result.status,
                        result.error,
                        int(time.time()),
                    ),
                )
            conn.commit()

    def save_equity(self, ts: int, equity: float) -> None:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO equity_snapshots (ts, equity)
                    VALUES (%s, %s)
                    """,
                    (int(ts), float(equity)),
                )
            conn.commit()

    def save_risk_event(self, event_type: str, reason: str, ts: Optional[int] = None) -> None:
        """Record halt, resume, or kill switch events."""
        now = ts if ts is not None else int(time.time())
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO risk_events (event_type, reason, ts)
                    VALUES (%s, %s, %s)
                    """,
                    (event_type, reason, now),
                )
            conn.commit()

    def get_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM trades ORDER BY id DESC LIMIT %s",
                    (limit,),
                )
                return [dict(row) for row in cur.fetchall()]

    def get_equity_curve(self, limit: int = 1000) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM equity_snapshots ORDER BY ts ASC LIMIT %s",
                    (limit,),
                )
                return [dict(row) for row in cur.fetchall()]

    def get_signals(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM signals ORDER BY id DESC LIMIT %s",
                    (limit,),
                )
                return [dict(row) for row in cur.fetchall()]

    def get_risk_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM risk_events ORDER BY id DESC LIMIT %s",
                    (limit,),
                )
                return [dict(row) for row in cur.fetchall()]


class SQLiteStore(Store):
    """SQLite implementation fallback for local development or testing without Postgres."""

    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS risk_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT,
                    reason TEXT,
                    ts INTEGER
                )
            """)

    def save_signal(self, signal: Signal, decision: RiskDecision) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO signals (symbol, side, entry_price, stop_loss, take_profit, reason, approved, approved_size, ts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    signal.symbol,
                    signal.side,
                    signal.entry_price,
                    signal.stop_loss,
                    signal.take_profit,
                    signal.reason,
                    1 if decision.approved else 0,
                    decision.size,
                    signal.ts,
                ),
            )

    def save_trade(self, order: OrderRequest, result: OrderResult) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO trades (symbol, side, size, entry_price, client_order_id, order_id, status, error, ts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    order.symbol,
                    order.side,
                    order.size,
                    order.entry_price,
                    order.client_order_id,
                    result.order_id,
                    result.status,
                    result.error,
                    int(time.time()),
                ),
            )

    def save_equity(self, ts: int, equity: float) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO equity_snapshots (ts, equity) VALUES (?, ?)",
                (ts, equity),
            )

    def save_risk_event(self, event_type: str, reason: str, ts: Optional[int] = None) -> None:
        now = ts if ts is not None else int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO risk_events (event_type, reason, ts) VALUES (?, ?, ?)",
                (event_type, reason, now),
            )

    def get_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_equity_curve(self, limit: int = 1000) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM equity_snapshots ORDER BY ts ASC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_signals(self, limit: int = 100) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_risk_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM risk_events ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]


def get_default_store() -> Store:
    """Factory creating PostgresStore if configured and reachable, else SQLiteStore."""
    if settings.DB_PASSWORD and PSYCOPG2_AVAILABLE:
        try:
            store = PostgresStore()
            return store
        except Exception as e:
            logger.warning(f"[storage] Could not connect to PostgreSQL ({e}). Falling back to SQLiteStore.")
    return SQLiteStore()
