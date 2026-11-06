"""Per-owner state of gap signals (saved, dismissed, already explored, turned into an idea), keyed by scope."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

from app.core.config import settings
from app.services.library.store import LibraryStore, _Session, now

STATES = ("saved", "dismissed", "explored", "idea")
_SCHEMA = """create table if not exists gap_signal_states (
    owner_id text not null,
    scope_key text not null,
    signal_id text not null,
    state text not null,
    snapshot text not null default '{}',
    updated_at text not null,
    primary key (owner_id, scope_key, signal_id)
)"""
_READY: set[str] = set()


class GapStateStore:
    @contextmanager
    def _db(self):
        connection = LibraryStore._connect()
        try:
            cursor = connection.cursor()
            if settings.database_url not in _READY:
                cursor.execute(_SCHEMA)
                connection.commit()
                _READY.add(settings.database_url)
            yield _Session(connection, cursor)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def states(self, owner: str, scope_key: str | None = None) -> list[dict[str, Any]]:
        with self._db() as db:
            if scope_key:
                rows = db.all("select scope_key, signal_id, state, snapshot, updated_at from gap_signal_states where owner_id=? and scope_key=? order by updated_at desc", (owner, scope_key))
            else:
                rows = db.all("select scope_key, signal_id, state, snapshot, updated_at from gap_signal_states where owner_id=? order by updated_at desc", (owner,))
        return [{"scope_key": row[0], "signal_id": row[1], "state": row[2], "snapshot": json.loads(row[3] or "{}"), "updated_at": row[4]} for row in rows]

    def set_state(self, owner: str, scope_key: str, signal_id: str, state: str | None, snapshot: dict[str, Any] | None = None) -> None:
        with self._db() as db:
            db.run("delete from gap_signal_states where owner_id=? and scope_key=? and signal_id=?", (owner, scope_key, signal_id))
            if state in STATES:
                db.run("insert into gap_signal_states (owner_id, scope_key, signal_id, state, snapshot, updated_at) values (?,?,?,?,?,?)",
                       (owner, scope_key, signal_id, state, json.dumps(snapshot or {}, ensure_ascii=False)[:20000], now()))
