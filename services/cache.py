"""SQLite-backed cache for fetched payloads.

The point is API-call economy: the Alpha Vantage free tier permits 5 calls per
minute, so re-typing a ticker you already looked up should not cost a call.

The architectural point is indirection. :class:`CachedClient` implements the
same ``fetch_stock_data(symbol) -> dict`` interface as ``APIClient`` and
``DemoClient`` and wraps one of them. The UI holds a client and calls it; it
never learns whether the bytes came from the network, from disk, or from a
bundled sample. Swapping the storage engine, or dropping caching entirely,
touches this file and nothing else.

Whole JSON payloads are stored rather than parsed rows: the cache stays
agnostic to the schema, so changing how ``DataProcessor`` cleans data never
invalidates cached entries.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

DEFAULT_TTL_SECONDS = 6 * 60 * 60  # Daily bars change at most once a day.
DEFAULT_DB_PATH = Path.home() / ".insightflow" / "cache.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS payloads (
    symbol      TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    fetched_at  REAL NOT NULL
);
"""


class PayloadCache:
    """Thin key-value store over SQLite, keyed by ticker symbol."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self.db_path = Path(db_path)
        self.ttl_seconds = ttl_seconds
        if self.db_path.parent and str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute(SCHEMA)
        self._conn.commit()

    @staticmethod
    def _key(symbol: str) -> str:
        return symbol.strip().upper()

    def get(self, symbol: str, now: float | None = None) -> dict | None:
        """Return the cached payload, or None if absent or expired."""
        now = time.time() if now is None else now
        row = self._conn.execute(
            "SELECT payload, fetched_at FROM payloads WHERE symbol = ?", (self._key(symbol),)
        ).fetchone()
        if row is None:
            return None

        payload_text, fetched_at = row
        if self.ttl_seconds is not None and now - fetched_at > self.ttl_seconds:
            return None
        try:
            return json.loads(payload_text)
        except json.JSONDecodeError:
            # A corrupt row should degrade to a cache miss, never crash a lookup.
            self.delete(symbol)
            return None

    def set(self, symbol: str, payload: dict, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self._conn.execute(
            "INSERT INTO payloads (symbol, payload, fetched_at) VALUES (?, ?, ?) "
            "ON CONFLICT(symbol) DO UPDATE SET payload = excluded.payload, "
            "fetched_at = excluded.fetched_at",
            (self._key(symbol), json.dumps(payload), now),
        )
        self._conn.commit()

    def delete(self, symbol: str) -> None:
        self._conn.execute("DELETE FROM payloads WHERE symbol = ?", (self._key(symbol),))
        self._conn.commit()

    def clear(self) -> None:
        self._conn.execute("DELETE FROM payloads")
        self._conn.commit()

    def symbols(self) -> list[str]:
        return [r[0] for r in self._conn.execute("SELECT symbol FROM payloads ORDER BY symbol")]

    def close(self) -> None:
        self._conn.close()


class CachedClient:
    """Decorator that serves an inner client's results from SQLite when fresh."""

    def __init__(self, inner, cache: PayloadCache | None = None):
        self.inner = inner
        self.cache = cache if cache is not None else PayloadCache()
        #: Set after each call so the UI can show provenance without asking how.
        self.last_source: str | None = None

    def fetch_stock_data(self, symbol: str) -> dict:
        cached = self.cache.get(symbol)
        if cached is not None:
            self.last_source = "cache"
            return cached

        payload = self.inner.fetch_stock_data(symbol)
        # Only successful fetches reach here -- errors propagate uncached, so a
        # transient rate-limit response never poisons the cache.
        self.cache.set(symbol, payload)
        self.last_source = self._inner_source()
        return payload

    def _inner_source(self) -> str:
        """Label the wrapped client so the status bar does not claim a demo
        lookup came off the network."""
        return "sample data" if type(self.inner).__name__ == "DemoClient" else "network"
