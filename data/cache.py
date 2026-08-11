"""The shared store.

One poller writes; the agents and the dashboard read. Nothing fetches on demand.
This is what keeps us inside the free-tier rate limits (cricket is 100 hits/day,
Jolpica 200/hour) and what makes the dashboard instant.

The important behaviour is stale-while-error: a failed fetch never destroys the
last good payload. A dead upstream shows a stale tile with a timestamp, not a
blank one.
"""
import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from config.settings import CACHE_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    source        TEXT PRIMARY KEY,
    payload       TEXT,
    fetched_at    REAL,
    ttl           REAL NOT NULL,
    last_error    TEXT,
    last_error_at REAL
);
"""


@dataclass
class Entry:
    source: str
    payload: Any
    fetched_at: float | None
    ttl: float
    last_error: str | None
    last_error_at: float | None

    @property
    def age(self) -> float | None:
        """Seconds since this payload was fetched, or None if never fetched."""
        return None if self.fetched_at is None else time.time() - self.fetched_at

    @property
    def is_stale(self) -> bool:
        """True when the payload has outlived its TTL and should be refreshed."""
        return self.age is None or self.age > self.ttl

    @property
    def is_healthy(self) -> bool:
        """A source is healthy when it has data and its last fetch succeeded."""
        if self.payload is None:
            return False
        if self.last_error_at is None:
            return True
        return (self.fetched_at or 0) >= self.last_error_at


class Cache:
    def __init__(self, path: Path = CACHE_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        # WAL lets the dashboard read while the poller writes.
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def put(self, source: str, payload: Any, ttl: float) -> None:
        """Record a successful fetch, clearing any previous error."""
        with self._conn() as c:
            c.execute(
                """INSERT INTO cache (source, payload, fetched_at, ttl, last_error, last_error_at)
                   VALUES (?, ?, ?, ?, NULL, NULL)
                   ON CONFLICT(source) DO UPDATE SET
                       payload=excluded.payload,
                       fetched_at=excluded.fetched_at,
                       ttl=excluded.ttl,
                       last_error=NULL,
                       last_error_at=NULL""",
                (source, json.dumps(payload), time.time(), ttl),
            )

    def record_failure(self, source: str, error: str, ttl: float) -> None:
        """Note a failed fetch. Deliberately leaves any existing payload intact."""
        with self._conn() as c:
            c.execute(
                """INSERT INTO cache (source, payload, fetched_at, ttl, last_error, last_error_at)
                   VALUES (?, NULL, NULL, ?, ?, ?)
                   ON CONFLICT(source) DO UPDATE SET
                       last_error=excluded.last_error,
                       last_error_at=excluded.last_error_at""",
                (source, ttl, error[:500], time.time()),
            )

    def get(self, source: str) -> Entry | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT source, payload, fetched_at, ttl, last_error, last_error_at "
                "FROM cache WHERE source = ?",
                (source,),
            ).fetchone()
        return self._to_entry(row) if row else None

    def all(self) -> list[Entry]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT source, payload, fetched_at, ttl, last_error, last_error_at "
                "FROM cache ORDER BY source"
            ).fetchall()
        return [self._to_entry(r) for r in rows]

    @staticmethod
    def _to_entry(row: tuple) -> Entry:
        source, payload, fetched_at, ttl, last_error, last_error_at = row
        return Entry(
            source=source,
            payload=json.loads(payload) if payload is not None else None,
            fetched_at=fetched_at,
            ttl=ttl,
            last_error=last_error,
            last_error_at=last_error_at,
        )
