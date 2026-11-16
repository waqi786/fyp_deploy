"""Listening sessions (credits per chunk), resume positions and the "Listen later" queue.

Credits
  browser voice = free. Neural voice = LISTEN_NEURAL_CREDITS_PER_MINUTE (default 1) per started minute of text.
  start_session reserves the estimate for the whole request; every synthesized chunk adds to `used_chars`;
  finish (or stop) commits only what was actually spoken and refunds the rest. Cached audio is still counted
  for the listener (the cache saves compute, the plan still meters listening) unless LISTEN_CACHE_FREE=1.
"""

from __future__ import annotations

import json
import math
import os
import uuid
from typing import Any

from app.services.credits import service as credits
from app.services.listen.script import CHARS_PER_MINUTE, script_family
from app.services.sqlstore import database, now_iso

SCHEMA = [
    """create table if not exists listen_sessions (
        id text primary key, user_key text not null, voice text not null, language text not null,
        reservation_id text, reserved_credits integer not null default 0, estimated_chars integer not null default 0,
        used_chars integer not null default 0, chunks integer not null default 0, status text not null,
        created_at text not null, updated_at text not null)""",
    "create index if not exists ix_listen_sessions_user on listen_sessions (user_key, created_at)",
    """create table if not exists listen_progress (
        user_key text not null, item_id text not null, kind text not null, title text not null,
        language text not null, section integer not null default 0, sentence integer not null default 0,
        total_sections integer not null default 0, percent real not null default 0, voice text, rate real not null default 1,
        updated_at text not null, primary key (user_key, item_id))""",
    """create table if not exists listen_queue (
        id text primary key, user_key text not null, item_id text not null, kind text not null, title text not null,
        payload text not null, position integer not null, added_at text not null)""",
    "create index if not exists ix_listen_queue_user on listen_queue (user_key, position)",
]


class ListenError(Exception):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def _db():
    return database("listen", SCHEMA)


def credits_per_minute() -> int:
    try:
        return max(0, int(os.getenv("LISTEN_NEURAL_CREDITS_PER_MINUTE", "1")))
    except ValueError:
        return 1


def estimate(characters: int, language: str, tier: str) -> dict[str, Any]:
    minutes = characters / CHARS_PER_MINUTE[script_family(language)]
    cost = 0 if tier != "neural" else math.ceil(minutes) * credits_per_minute()
    return {"minutes": round(minutes, 1), "credits": cost, "tier": tier}


def start_session(user_key: str, *, voice: str, language: str, characters: int, plan: str = "free") -> dict[str, Any]:
    tier = "neural" if voice.startswith("neural:") else "browser"
    quote = estimate(max(0, characters), language, tier)
    reservation = None
    if quote["credits"]:
        try:
            reservation = credits.get_credit_service().reserve(user_key, "listen_neural", quote["credits"], plan)
        except credits.CreditLimitReached as error:
            raise ListenError("limit_reached", 402) from error
    session_id = f"ls_{uuid.uuid4().hex[:20]}"
    with _db() as db:
        db.run(
            "insert into listen_sessions (id, user_key, voice, language, reservation_id, reserved_credits, estimated_chars, used_chars, chunks, status, created_at, updated_at) values (?,?,?,?,?,?,?,?,?,?,?,?)",
            (session_id, user_key, voice, language, reservation, quote["credits"], characters, 0, 0, "open", now_iso(), now_iso()),
        )
    return {"session_id": session_id, **quote}


def session(user_key: str, session_id: str) -> dict[str, Any]:
    with _db() as db:
        row = db.one("select * from listen_sessions where id = ? and user_key = ?", (session_id, user_key))
    if not row:
        raise ListenError("not_found", 404)
    return row


def record_chunk(user_key: str, session_id: str, characters: int) -> dict[str, Any]:
    row = session(user_key, session_id)
    if row["status"] != "open":
        raise ListenError("session_closed", 409)
    # A session may not speak much more than it reserved (protects the ledger from an unlimited stream).
    if row["reserved_credits"] and row["used_chars"] + characters > max(row["estimated_chars"] * 1.15, row["estimated_chars"] + 400):
        raise ListenError("session_exhausted", 409)
    with _db() as db:
        db.run("update listen_sessions set used_chars = used_chars + ?, chunks = chunks + 1, updated_at = ? where id = ?", (characters, now_iso(), session_id))
    return session(user_key, session_id)


def finish_session(user_key: str, session_id: str) -> dict[str, Any]:
    row = session(user_key, session_id)
    if row["status"] != "open":
        return {"session_id": session_id, "charged": row.get("reserved_credits", 0) if row["status"] == "committed" else 0, "status": row["status"]}
    charged = 0
    service = credits.get_credit_service()
    if row["reservation_id"]:
        charged = min(row["reserved_credits"], estimate(row["used_chars"], row["language"], "neural")["credits"]) if row["used_chars"] else 0
        if charged:
            service.commit(row["reservation_id"], charged)
        else:
            service.refund(row["reservation_id"])
    with _db() as db:
        db.run("update listen_sessions set status = ?, reserved_credits = ?, updated_at = ? where id = ?", ("committed" if charged else "refunded", charged, now_iso(), session_id))
    return {"session_id": session_id, "charged": charged, "status": "committed" if charged else "refunded"}


# ------------------------------------------------------------------ resume positions

def save_progress(user_key: str, item: dict[str, Any]) -> dict[str, Any]:
    values = (
        user_key, str(item["item_id"])[:200], str(item.get("kind") or "paper")[:20], str(item.get("title") or "")[:300], str(item.get("language") or "en")[:16],
        max(0, int(item.get("section") or 0)), max(0, int(item.get("sentence") or 0)), max(0, int(item.get("total_sections") or 0)),
        min(1.0, max(0.0, float(item.get("percent") or 0))), (str(item["voice"])[:80] if item.get("voice") else None), min(2.0, max(0.5, float(item.get("rate") or 1))), now_iso(),
    )
    with _db() as db:
        db.run("delete from listen_progress where user_key = ? and item_id = ?", (user_key, values[1]))
        db.run(
            "insert into listen_progress (user_key, item_id, kind, title, language, section, sentence, total_sections, percent, voice, rate, updated_at) values (?,?,?,?,?,?,?,?,?,?,?,?)",
            values,
        )
        return db.one("select * from listen_progress where user_key = ? and item_id = ?", (user_key, values[1])) or {}


def progress(user_key: str, item_id: str | None = None) -> list[dict[str, Any]]:
    with _db() as db:
        if item_id:
            row = db.one("select * from listen_progress where user_key = ? and item_id = ?", (user_key, item_id))
            return [row] if row else []
        return db.all("select * from listen_progress where user_key = ? order by updated_at desc limit 20", (user_key,))


# ------------------------------------------------------------------ queue ("Listen later")

MAX_QUEUE = 50


def queue(user_key: str) -> list[dict[str, Any]]:
    with _db() as db:
        rows = db.all("select * from listen_queue where user_key = ? order by position, added_at", (user_key,))
    for row in rows:
        row["payload"] = json.loads(row["payload"] or "{}")
    return rows


def enqueue(user_key: str, item: dict[str, Any]) -> list[dict[str, Any]]:
    item_id = str(item["item_id"])[:200]
    with _db() as db:
        if db.one("select id from listen_queue where user_key = ? and item_id = ?", (user_key, item_id)):
            pass
        else:
            count = int(db.scalar("select count(*) from listen_queue where user_key = ?", (user_key,)) or 0)
            if count >= MAX_QUEUE:
                raise ListenError("queue_full", 409)
            position = int(db.scalar("select coalesce(max(position), -1) from listen_queue where user_key = ?", (user_key,)) or -1) + 1
            db.run(
                "insert into listen_queue (id, user_key, item_id, kind, title, payload, position, added_at) values (?,?,?,?,?,?,?,?)",
                (f"lq_{uuid.uuid4().hex[:16]}", user_key, item_id, str(item.get("kind") or "paper")[:20], str(item.get("title") or "")[:300], json.dumps(item.get("payload") or {})[:20000], position, now_iso()),
            )
    return queue(user_key)


def dequeue(user_key: str, entry_id: str) -> list[dict[str, Any]]:
    with _db() as db:
        db.run("delete from listen_queue where user_key = ? and (id = ? or item_id = ?)", (user_key, entry_id, entry_id))
    return queue(user_key)


def reorder(user_key: str, ids: list[str]) -> list[dict[str, Any]]:
    with _db() as db:
        for position, entry_id in enumerate(ids):
            db.run("update listen_queue set position = ? where user_key = ? and id = ?", (position, user_key, entry_id))
    return queue(user_key)
