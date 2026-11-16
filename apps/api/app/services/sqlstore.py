"""Small shared database helper for feature stores (billing, teams).

Same rules as the Library store: one `settings.database_url` (SQLite in development, PostgreSQL in production),
tables created on first use per database, `?` placeholders translated for PostgreSQL, short-lived connections.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings

_READY: set[tuple[str, str]] = set()


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _connect():  # noqa: ANN202
    url = settings.database_url
    if url.startswith("sqlite:///"):
        path = url.removeprefix("sqlite:///")
        if os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        connection = sqlite3.connect(path, timeout=10)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection
    import psycopg

    return psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://", 1), connect_timeout=5)


class Session:
    def __init__(self, connection: Any, cursor: Any) -> None:
        self.connection = connection
        self.cursor = cursor
        self.sqlite = isinstance(connection, sqlite3.Connection)

    def _sql(self, sql: str) -> str:
        return sql if self.sqlite else sql.replace("?", "%s")

    def run(self, sql: str, values: Sequence[Any] = ()) -> int:
        self.cursor.execute(self._sql(sql), tuple(values))
        return self.cursor.rowcount

    def one(self, sql: str, values: Sequence[Any] = ()) -> dict[str, Any] | None:
        self.cursor.execute(self._sql(sql), tuple(values))
        row = self.cursor.fetchone()
        if row is None:
            return None
        return dict(zip([column[0] for column in self.cursor.description], row))

    def all(self, sql: str, values: Sequence[Any] = ()) -> list[dict[str, Any]]:
        self.cursor.execute(self._sql(sql), tuple(values))
        names = [column[0] for column in self.cursor.description]
        return [dict(zip(names, row)) for row in self.cursor.fetchall()]

    def scalar(self, sql: str, values: Sequence[Any] = ()) -> Any:
        self.cursor.execute(self._sql(sql), tuple(values))
        row = self.cursor.fetchone()
        return row[0] if row else None


@contextmanager
def database(name: str, schema: Sequence[str]) -> Iterator[Session]:
    """Open a transaction; creates `schema` the first time `name` is used on this database."""
    connection = _connect()
    try:
        cursor = connection.cursor()
        key = (settings.database_url, name)
        if key not in _READY:
            for statement in schema:
                cursor.execute(statement)
            connection.commit()
            _READY.add(key)
        yield Session(connection, cursor)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
