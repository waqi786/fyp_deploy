"""Credits: estimate → reserve → commit / refund, with Claude-like usage windows.

Limits per plan (configurable with CREDIT_PLAN_LIMITS, JSON):
  session = rolling 5 hours, week = rolling 7 days, month = calendar month (UTC).
Reservations count against limits immediately, so two parallel requests cannot overspend. A reservation that is
never committed or refunded (crash) stops counting after RESERVATION_TTL_SECONDS.

Storage: a small SQLite ledger (CREDITS_DB_PATH). It is safe for one server; move the same table to PostgreSQL
when running several API instances.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

SESSION_SECONDS = 5 * 60 * 60
WEEK_SECONDS = 7 * 24 * 60 * 60
RESERVATION_TTL_SECONDS = 15 * 60

DEFAULT_PLAN_LIMITS: dict[str, dict[str, int]] = {
    "free": {"session": 25, "week": 120, "month": 300},
    "pro": {"session": 250, "week": 1500, "month": 5000},
    "team": {"session": 300, "week": 2000, "month": 7000},
    "institution": {"session": 400, "week": 3000, "month": 12000},
}

DEFAULT_ACTION_COSTS: dict[str, int] = {
    "search": 0,
    "research": 5,
    "ask": 1,
    "summary": 2,
    "chat": 1,
    "translate_pages": 1,  # one call translates up to 5 pages
}


class CreditLimitReached(Exception):
    def __init__(self, scope: str, resets_at: float):
        super().__init__(f"{scope} limit reached")
        self.scope = scope
        self.resets_at = resets_at


@dataclass(frozen=True)
class WindowUsage:
    scope: str
    used: int
    limit: int
    resets_at: float

    def as_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "used": self.used,
            "limit": self.limit,
            "remaining": max(0, self.limit - self.used),
            "percent": round(min(1.0, self.used / self.limit), 3) if self.limit else 0.0,
            "resets_at": datetime.fromtimestamp(self.resets_at, tz=timezone.utc).isoformat(),
        }


def _json_env(name: str, default: dict) -> dict:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else default
    except (ValueError, TypeError):
        logger.warning("Invalid %s; using defaults", name)
        return default


def _month_bounds(now: float) -> tuple[float, float]:
    current = datetime.fromtimestamp(now, tz=timezone.utc)
    start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start.timestamp(), end.timestamp()


class CreditService:
    def __init__(self, db_path: str | None = None) -> None:
        self._path = Path(db_path or os.getenv("CREDITS_DB_PATH", "storage/credits.sqlite3"))
        self._lock = threading.Lock()
        self._ready = False

    # ------------------------------------------------------------------ configuration

    @staticmethod
    def cost(action: str) -> int:
        costs = {**DEFAULT_ACTION_COSTS, **_json_env("CREDIT_ACTION_COSTS", {})}
        try:
            return max(0, int(costs.get(action, 0)))
        except (TypeError, ValueError):
            return DEFAULT_ACTION_COSTS.get(action, 0)

    @staticmethod
    def limits(plan: str) -> dict[str, int]:
        plans = {**DEFAULT_PLAN_LIMITS, **_json_env("CREDIT_PLAN_LIMITS", {})}
        return plans.get((plan or "free").lower(), plans["free"])

    # ------------------------------------------------------------------ storage

    def _connect(self) -> sqlite3.Connection:
        if not self._ready:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self._path, timeout=5) as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS credit_events ("
                    " id TEXT PRIMARY KEY, user_key TEXT NOT NULL, action TEXT NOT NULL, amount INTEGER NOT NULL,"
                    " status TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL)"
                )
                connection.execute("CREATE INDEX IF NOT EXISTS credit_events_user_time ON credit_events(user_key, created_at)")
            self._ready = True
        return sqlite3.connect(self._path, timeout=5)

    @staticmethod
    def _counted_sum(connection: sqlite3.Connection, user_key: str, since: float, now: float) -> tuple[int, float | None]:
        row = connection.execute(
            "SELECT COALESCE(SUM(amount), 0), MIN(created_at) FROM credit_events"
            " WHERE user_key = ? AND created_at >= ?"
            " AND (status = 'committed' OR (status = 'reserved' AND created_at >= ?))",
            (user_key, since, now - RESERVATION_TTL_SECONDS),
        ).fetchone()
        return int(row[0] or 0), row[1]

    def _windows(self, connection: sqlite3.Connection, user_key: str, plan: str, now: float) -> list[WindowUsage]:
        limits = self.limits(plan)
        session_used, session_oldest = self._counted_sum(connection, user_key, now - SESSION_SECONDS, now)
        week_used, week_oldest = self._counted_sum(connection, user_key, now - WEEK_SECONDS, now)
        month_start, month_end = _month_bounds(now)
        month_used, _ = self._counted_sum(connection, user_key, month_start, now)
        return [
            WindowUsage("session", session_used, int(limits["session"]), (session_oldest or now) + SESSION_SECONDS),
            WindowUsage("week", week_used, int(limits["week"]), (week_oldest or now) + WEEK_SECONDS),
            WindowUsage("month", month_used, int(limits["month"]), month_end),
        ]

    # ------------------------------------------------------------------ public API

    def usage(self, user_key: str, plan: str = "free") -> dict[str, object]:
        now = time.time()
        with self._lock, self._connect() as connection:
            windows = self._windows(connection, user_key, plan, now)
        return {"plan": plan, "windows": [window.as_dict() for window in windows]}

    def reserve(self, user_key: str, action: str, amount: int | None = None, plan: str = "free") -> str | None:
        """Hold credits for an action. Returns None for free actions. Raises CreditLimitReached."""
        amount = self.cost(action) if amount is None else max(0, int(amount))
        if amount == 0:
            return None
        now = time.time()
        reservation_id = uuid.uuid4().hex
        with self._lock, self._connect() as connection:
            for window in self._windows(connection, user_key, plan, now):
                if window.limit and window.used + amount > window.limit:
                    raise CreditLimitReached(window.scope, window.resets_at)
            connection.execute(
                "INSERT INTO credit_events (id, user_key, action, amount, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'reserved', ?, ?)",
                (reservation_id, user_key, action, amount, now, now),
            )
        return reservation_id

    def commit(self, reservation_id: str | None, amount: int | None = None) -> None:
        """Charge a reservation (optionally a smaller final amount, e.g. 0 for a cached answer)."""
        if not reservation_id:
            return
        with self._lock, self._connect() as connection:
            if amount is None:
                connection.execute("UPDATE credit_events SET status = 'committed', updated_at = ? WHERE id = ? AND status = 'reserved'", (time.time(), reservation_id))
            else:
                connection.execute(
                    "UPDATE credit_events SET status = 'committed', amount = MIN(amount, ?), updated_at = ? WHERE id = ? AND status = 'reserved'",
                    (max(0, int(amount)), time.time(), reservation_id),
                )

    def refund(self, reservation_id: str | None) -> None:
        if not reservation_id:
            return
        with self._lock, self._connect() as connection:
            connection.execute("UPDATE credit_events SET status = 'refunded', updated_at = ? WHERE id = ? AND status = 'reserved'", (time.time(), reservation_id))


_default_service: CreditService | None = None


def get_credit_service() -> CreditService:
    global _default_service
    if _default_service is None:
        _default_service = CreditService()
    return _default_service
