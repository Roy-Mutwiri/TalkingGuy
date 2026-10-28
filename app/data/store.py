"""SQLite cache of OHLCV candles. Candles are plain dicts:
   {"time": unix_seconds, "open": f, "high": f, "low": f, "close": f, "volume": f}
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

Candle = dict

TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}


class CandleStore:
    def __init__(self, path: str | Path = "data_cache/candles.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS candles (
                 symbol TEXT NOT NULL, tf TEXT NOT NULL, time INTEGER NOT NULL,
                 open REAL, high REAL, low REAL, close REAL, volume REAL,
                 PRIMARY KEY (symbol, tf, time))"""
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS coverage (
                 symbol TEXT NOT NULL, tf TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
                 PRIMARY KEY (symbol, tf, start))"""
        )
        self._conn.commit()

    def upsert(self, symbol: str, tf: str, candles: list[Candle]) -> int:
        if not candles:
            return 0
        rows = [(symbol, tf, int(c["time"]), c["open"], c["high"], c["low"], c["close"], c.get("volume", 0.0)) for c in candles]
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO candles (symbol, tf, time, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?,?)", rows
            )
            self._conn.commit()
        return len(rows)

    def mark_covered(self, symbol: str, tf: str, start: int, end: int) -> None:
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO coverage (symbol, tf, start, end) VALUES (?,?,?,?)", (symbol, tf, start, end))
            self._conn.commit()

    def is_covered(self, symbol: str, tf: str, start: int, end: int) -> bool:
        with self._lock:
            rows = self._conn.execute(
                "SELECT start, end FROM coverage WHERE symbol=? AND tf=? AND start<=? AND end>=? LIMIT 1", (symbol, tf, start, end)
            ).fetchall()
        return bool(rows)

    def get_range(self, symbol: str, tf: str, start: int, end: int) -> list[Candle]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT time, open, high, low, close, volume FROM candles WHERE symbol=? AND tf=? AND time>=? AND time<? ORDER BY time",
                (symbol, tf, start, end),
            ).fetchall()
        return [{"time": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]} for r in rows]

    def last(self, symbol: str, tf: str, n: int) -> list[Candle]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT time, open, high, low, close, volume FROM candles WHERE symbol=? AND tf=? ORDER BY time DESC LIMIT ?",
                (symbol, tf, n),
            ).fetchall()
        rows.reverse()
        return [{"time": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]} for r in rows]

    def bounds(self, symbol: str, tf: str) -> tuple[int, int] | None:
        with self._lock:
            r = self._conn.execute("SELECT MIN(time), MAX(time) FROM candles WHERE symbol=? AND tf=?", (symbol, tf)).fetchone()
        return (r[0], r[1]) if r and r[0] is not None else None

    def close(self) -> None:
        with self._lock:
            self._conn.close()
