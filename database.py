import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL,
    symbol TEXT,
    side TEXT,
    quantity REAL,
    reason TEXT,
    dry_run INTEGER
);
"""


class TradeDB:
    def __init__(self, path: str = "trades.db"):
        self.conn = sqlite3.connect(path)
        self.conn.execute(SCHEMA)
        self.conn.commit()

    def log_trade(self, symbol: str, side: str, quantity: float, reason: str, dry_run: bool):
        self.conn.execute(
            "INSERT INTO trades (ts, symbol, side, quantity, reason, dry_run) VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), symbol, side, quantity, reason, int(dry_run)),
        )
        self.conn.commit()
