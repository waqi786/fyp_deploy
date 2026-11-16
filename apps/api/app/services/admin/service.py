"""Admin console data: business metrics, users (plan, usage, credit grants, suspension), feature flags, jobs with
a dead-letter queue, status incidents and an append-only audit log.

Internal data is allowed here only. Every endpoint that uses this module is behind the admin role, enforced on the
server (ADMIN_USER_IDS, verified sign-in in production). Every change an admin makes writes an audit entry.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.billing import catalog
from app.services.billing import service as billing
from app.services.credits import service as credits
from app.services.sqlstore import database, now_iso

SCHEMA = [
    """create table if not exists admin_audit (
        id text primary key, actor_id text not null, action text not null, target text, detail text not null,
        created_at text not null)""",
    "create index if not exists ix_admin_audit_time on admin_audit (created_at)",
    """create table if not exists feature_flags (
        key text primary key, description text not null default '', enabled integer not null default 0,
        rollout integer not null default 100, allow_users text not null default '[]', updated_by text, updated_at text not null)""",
    """create table if not exists user_status (
        user_id text primary key, suspended integer not null default 0, reason text, note text, updated_by text, updated_at text not null)""",
    """create table if not exists dead_letters (
        id text primary key, kind text not null, source text not null, payload text not null, error text not null,
        attempts integer not null default 1, status text not null default 'failed', created_at text not null, updated_at text not null)""",
    """create table if not exists status_incidents (
        id text primary key, title text not null, component text not null, severity text not null, status text not null,
        message text not null, created_at text not null, updated_at text not null, resolved_at text)""",
]

FLAG_KEY_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_.-")
COMPONENTS = ("search", "reader", "listen", "billing", "ai", "catalog", "website")
SEVERITIES = ("minor", "major", "critical", "maintenance")
INCIDENT_STATES = ("investigating", "identified", "monitoring", "resolved")

# Flags the product ships with (created disabled/enabled on first read; admins change them at runtime).
DEFAULT_FLAGS: dict[str, tuple[str, bool]] = {
    "listen.neural_voices": ("Offer self-hosted neural voices in the player", True),
    "growth.referrals": ("Referral credits for inviting colleagues", True),
    "growth.newsletter": ("Newsletter / waitlist capture on the public site", True),
    "search.catalog_source": ("Include the Resora research catalog in Search", True),
    "insights.public_trends": ("Show catalog trends to signed-out visitors", False),
}


class AdminError(Exception):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def _db():
    return database("admin", SCHEMA)


def audit(actor: str, action: str, target: str | None = None, detail: dict[str, Any] | None = None) -> None:
    with _db() as db:
        db.run("insert into admin_audit (id, actor_id, action, target, detail, created_at) values (?,?,?,?,?,?)",
               (f"au_{uuid.uuid4().hex[:20]}", actor, action, target, json.dumps(detail or {}, default=str)[:4000], now_iso()))


def audit_log(limit: int = 100, action: str | None = None) -> list[dict[str, Any]]:
    with _db() as db:
        if action:
            rows = db.all("select * from admin_audit where action like ? order by created_at desc limit ?", (f"{action}%", limit))
        else:
            rows = db.all("select * from admin_audit order by created_at desc limit ?", (limit,))
    for row in rows:
        row["detail"] = json.loads(row["detail"] or "{}")
    return rows


# ------------------------------------------------------------------------------------------------ suspension

_suspended_cache: dict[str, tuple[float, bool]] = {}
_cache_lock = threading.Lock()


def is_suspended(user_id: str) -> bool:
    """Cached for 20 s so the request guard costs nothing on the hot path."""
    if not user_id or user_id == "anonymous":
        return False
    now = time.time()
    with _cache_lock:
        hit = _suspended_cache.get(user_id)
        if hit and hit[0] > now:
            return hit[1]
    try:
        with _db() as db:
            row = db.one("select suspended from user_status where user_id = ?", (user_id,))
        value = bool(row and row["suspended"])
    except Exception:  # noqa: BLE001 - a status lookup must never take the API down
        value = False
    with _cache_lock:
        _suspended_cache[user_id] = (now + 20, value)
    return value


def set_suspended(actor: str, user_id: str, suspended: bool, reason: str | None) -> dict[str, Any]:
    if actor == user_id:
        raise AdminError("cannot_suspend_self", 409)
    with _db() as db:
        db.run("delete from user_status where user_id = ?", (user_id,))
        db.run("insert into user_status (user_id, suspended, reason, updated_by, updated_at) values (?,?,?,?,?)", (user_id, int(suspended), (reason or "")[:300], actor, now_iso()))
    with _cache_lock:
        _suspended_cache.pop(user_id, None)
    audit(actor, "user.suspend" if suspended else "user.unsuspend", user_id, {"reason": reason})
    return {"user_id": user_id, "suspended": suspended, "reason": reason}


# ------------------------------------------------------------------------------------------------ users

def _credit_rows(since: float | None = None) -> list[tuple[str, str, int, str, float]]:
    service = credits.get_credit_service()
    try:
        with service._connect() as connection:
            if since is None:
                return connection.execute("select user_key, action, amount, status, created_at from credit_events").fetchall()
            return connection.execute("select user_key, action, amount, status, created_at from credit_events where created_at >= ?", (since,)).fetchall()
    except sqlite3.Error:
        return []


def _teams_db():
    from app.services.teams import store as teams_store

    return teams_store._db()


def _ensure_feature_tables() -> None:
    """Admin reads tables owned by other features; create them if those features have never been used."""
    with billing._db():
        pass
    with _teams_db():
        pass


def users(query: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
    _ensure_feature_tables()
    first_seen: dict[str, float] = {}
    last_seen: dict[str, float] = {}
    used_30d: Counter[str] = Counter()
    month_ago = time.time() - 30 * 86400
    for user_key, _action, amount, status, created_at in _credit_rows():
        if not user_key.startswith("user:"):
            continue
        user_id = user_key.split(":", 1)[1]
        first_seen[user_id] = min(first_seen.get(user_id, created_at), created_at)
        last_seen[user_id] = max(last_seen.get(user_id, created_at), created_at)
        if created_at >= month_ago and status in ("committed", "topup"):
            used_30d[user_id] += int(amount)
    with _db() as db:
        statuses = {row["user_id"]: row for row in db.all("select * from user_status")}
    with billing._db() as db:
        subs = {row["owner_id"]: row for row in db.all("select * from billing_subscriptions where status != 'canceled' order by created_at")}
        topups = {row["owner_id"]: int(row["balance"]) for row in db.all("select owner_id, sum(credits_total - credits_used) as balance from billing_topups group by owner_id")}
        for owner in db.all("select distinct owner_id from billing_invoices"):
            first_seen.setdefault(owner["owner_id"], 0)
    with _teams_db() as db:
        team_counts = {row["user_id"]: int(row["teams"]) for row in db.all("select user_id, count(*) as teams from team_members group by user_id")}
        names = {row["user_id"]: row["display_name"] for row in db.all("select user_id, display_name from team_members")}
    ids = set(first_seen) | set(subs) | set(team_counts) | set(statuses)
    needle = query.strip().lower()
    rows = []
    for user_id in ids:
        name = names.get(user_id, "")
        if needle and needle not in user_id.lower() and needle not in name.lower():
            continue
        sub = subs.get(user_id)
        rows.append({
            "user_id": user_id, "display_name": name, "plan": sub["plan"] if sub else "free", "subscription_status": sub["status"] if sub else None,
            "seats": int(sub["seats"]) if sub else 1, "credits_30d": used_30d.get(user_id, 0), "topup_balance": topups.get(user_id, 0),
            "teams": team_counts.get(user_id, 0), "suspended": bool(statuses.get(user_id, {}).get("suspended")),
            "first_seen": datetime.fromtimestamp(first_seen[user_id], tz=UTC).isoformat() if first_seen.get(user_id) else None,
            "last_seen": datetime.fromtimestamp(last_seen[user_id], tz=UTC).isoformat() if user_id in last_seen else None,
        })
    rows.sort(key=lambda row: (row["last_seen"] or "", row["user_id"]), reverse=True)
    return {"total": len(rows), "users": rows[offset: offset + limit]}


def user_detail(user_id: str) -> dict[str, Any]:
    plan, team_id, seats = billing.effective_plan(user_id)
    key = f"user:{user_id}"
    usage = credits.get_credit_service().usage(key, plan)
    history = credits.get_credit_service().history(key, time.time() - 30 * 86400, plan)
    with billing._db() as db:
        invoices = db.all("select id, number, kind, description, amount, currency, status, created_at from billing_invoices where owner_id = ? order by created_at desc limit 20", (user_id,))
        subs = db.all("select * from billing_subscriptions where owner_id = ? order by created_at desc limit 10", (user_id,))
        grants = db.all("select id, credits_total, credits_used, session_id, created_at from billing_topups where owner_id = ? order by created_at desc limit 20", (user_id,))
    with _teams_db() as db:
        teams = db.all("select t.id, t.name, m.role from team_members m join teams t on t.id = m.team_id where m.user_id = ?", (user_id,))
    with _db() as db:
        status = db.one("select * from user_status where user_id = ?", (user_id,))
        events = db.all("select * from admin_audit where target = ? order by created_at desc limit 30", (user_id,))
    for event in events:
        event["detail"] = json.loads(event["detail"] or "{}")
    return {
        "user_id": user_id, "plan": plan, "team_id": team_id, "seats": seats, "usage": usage, "history": history, "invoices": invoices,
        "subscriptions": subs, "credit_grants": grants, "teams": teams, "suspended": bool(status and status["suspended"]),
        "suspension_reason": (status or {}).get("reason"), "audit": events,
    }


def grant_credits(actor: str, user_id: str, amount: int, reason: str) -> dict[str, Any]:
    if amount <= 0 or amount > 100000:
        raise AdminError("invalid_amount", 422)
    grant = billing.grant_credits(user_id, amount, source=f"admin:{actor}")
    audit(actor, "user.grant_credits", user_id, {"credits": amount, "reason": reason, "grant_id": grant["id"]})
    return {"user_id": user_id, "credits": amount, "balance": billing.topup_balance(user_id)}


# ------------------------------------------------------------------------------------------------ metrics

def _monthly(sub: dict[str, Any]) -> int:
    amount = catalog.price(sub["plan"], sub["currency"], sub["interval"], int(sub["seats"] or 1))
    return round(amount / 12) if sub["interval"] == "year" else int(amount)


def overview() -> dict[str, Any]:
    _ensure_feature_tables()
    now = datetime.now(UTC)
    with billing._db() as db:
        subs = db.all("select * from billing_subscriptions where status != 'canceled'")
        invoices_30 = db.all("select amount, currency, kind, status, created_at from billing_invoices where created_at >= ?", ((now - timedelta(days=30)).isoformat(),))
        topups_sold = int(db.scalar("select coalesce(sum(credits_total), 0) from billing_topups where session_id is null or session_id not like 'grant:%'") or 0)
    mrr: dict[str, int] = defaultdict(int)
    plans: Counter[str] = Counter()
    states: Counter[str] = Counter()
    churn_risk = 0
    for sub in subs:
        states[sub["status"]] += 1
        plans[sub["plan"]] += 1
        if sub["status"] in ("active", "past_due"):
            mrr[sub["currency"]] += _monthly(sub)
        if sub["cancel_at_period_end"] or sub["status"] == "past_due":
            churn_risk += 1
    revenue: dict[str, int] = defaultdict(int)
    for invoice in invoices_30:
        if invoice["status"] == "paid":
            revenue[invoice["currency"]] += int(invoice["amount"])
        elif invoice["status"] == "refunded":
            revenue[invoice["currency"]] -= int(invoice["amount"])
    rows = _credit_rows()
    first: dict[str, float] = {}
    active_7: set[str] = set()
    active_30: set[str] = set()
    actions_30: Counter[str] = Counter()
    daily: Counter[str] = Counter()
    t7, t30 = time.time() - 7 * 86400, time.time() - 30 * 86400
    for user_key, action, amount, status, created_at in rows:
        if user_key.startswith(("user:", "guest:")):
            first[user_key] = min(first.get(user_key, created_at), created_at)
        if created_at >= t30:
            active_30.add(user_key)
            if status in ("committed", "topup"):
                actions_30[action] += int(amount)
                daily[datetime.fromtimestamp(created_at, tz=UTC).date().isoformat()] += int(amount)
        if created_at >= t7:
            active_7.add(user_key)
    signups_30 = sum(1 for key, ts in first.items() if ts >= t30 and key.startswith("user:"))
    activated = sum(1 for key, ts in first.items() if ts >= t30 and key.startswith("user:") and key in active_7)
    paying = states["active"] + states["past_due"]
    from app.services.growth import (
        service as growth,  # local import: growth imports admin flags
    )

    return {
        "mrr": dict(mrr), "revenue_30d": dict(revenue), "subscriptions": dict(states), "plans": dict(plans), "paying": paying,
        "trialing": states["trialing"], "churn_risk": churn_risk, "churn_risk_rate": round(churn_risk / paying, 3) if paying else 0,
        "signups_30d": signups_30, "activation_rate": round(activated / signups_30, 3) if signups_30 else 0,
        "active_users_7d": len(active_7), "active_users_30d": len(active_30), "credits_by_action_30d": dict(actions_30.most_common()),
        "credits_by_day": [{"day": day, "credits": daily[day]} for day in sorted(daily)][-30:], "credit_packs_sold": topups_sold,
        "traffic": growth.traffic_summary(30), "referrals": growth.referral_summary(), "waitlist": growth.waitlist_count(),
        "open_messages": growth.contact_count(status="open"),
    }


# ------------------------------------------------------------------------------------------------ feature flags

def _seed_flags(db) -> None:
    existing = {row["key"] for row in db.all("select key from feature_flags")}
    for key, (description, enabled) in DEFAULT_FLAGS.items():
        if key not in existing:
            db.run("insert into feature_flags (key, description, enabled, rollout, allow_users, updated_by, updated_at) values (?,?,?,?,?,?,?)", (key, description, int(enabled), 100, "[]", "system", now_iso()))


def flags() -> list[dict[str, Any]]:
    with _db() as db:
        _seed_flags(db)
        rows = db.all("select * from feature_flags order by key")
    for row in rows:
        row["enabled"] = bool(row["enabled"])
        row["allow_users"] = json.loads(row["allow_users"] or "[]")
    return rows


def set_flag(actor: str, key: str, *, enabled: bool, rollout: int = 100, description: str | None = None, allow_users: list[str] | None = None) -> dict[str, Any]:
    key = key.strip().lower()
    if not key or len(key) > 64 or not set(key) <= FLAG_KEY_CHARS:
        raise AdminError("invalid_flag", 422)
    rollout = max(0, min(100, int(rollout)))
    with _db() as db:
        _seed_flags(db)
        current = db.one("select * from feature_flags where key = ?", (key,))
        db.run("delete from feature_flags where key = ?", (key,))
        db.run("insert into feature_flags (key, description, enabled, rollout, allow_users, updated_by, updated_at) values (?,?,?,?,?,?,?)",
               (key, (description if description is not None else (current or {}).get("description", ""))[:300], int(enabled), rollout, json.dumps((allow_users if allow_users is not None else json.loads((current or {}).get("allow_users") or "[]"))[:500]), actor, now_iso()))
    audit(actor, "flag.update", key, {"enabled": enabled, "rollout": rollout, "before": {"enabled": bool((current or {}).get("enabled")), "rollout": (current or {}).get("rollout")}})
    return next(flag for flag in flags() if flag["key"] == key)


def delete_flag(actor: str, key: str) -> None:
    with _db() as db:
        db.run("delete from feature_flags where key = ?", (key,))
    audit(actor, "flag.delete", key, {})


def flag_enabled(key: str, user_key: str | None = None, flag_rows: list[dict[str, Any]] | None = None) -> bool:
    """Deterministic percentage rollout: the same user always lands in the same bucket for a flag."""
    row = next((flag for flag in (flag_rows if flag_rows is not None else flags()) if flag["key"] == key), None)
    if not row or not row["enabled"]:
        return False
    if user_key and user_key in row["allow_users"]:
        return True
    if row["rollout"] >= 100:
        return True
    if not user_key or row["rollout"] <= 0:
        return False
    bucket = int(hashlib.sha256(f"{key}:{user_key}".encode()).hexdigest()[:8], 16) % 100
    return bucket < row["rollout"]


def flags_for(user_key: str | None) -> dict[str, bool]:
    rows = flags()
    return {row["key"]: flag_enabled(row["key"], user_key, rows) for row in rows}


# ------------------------------------------------------------------------------------------------ jobs / dead letters

def record_dead_letter(kind: str, source: str, payload: dict[str, Any], error: str) -> str:
    entry_id = f"dl_{uuid.uuid4().hex[:20]}"
    with _db() as db:
        db.run("insert into dead_letters (id, kind, source, payload, error, attempts, status, created_at, updated_at) values (?,?,?,?,?,?,?,?,?)",
               (entry_id, kind, source, json.dumps(payload, default=str)[:200000], error[:500], 1, "failed", now_iso(), now_iso()))
    return entry_id


def dead_letters(status: str | None = None) -> list[dict[str, Any]]:
    with _db() as db:
        rows = db.all("select id, kind, source, error, attempts, status, created_at, updated_at from dead_letters" + (" where status = ?" if status else "") + " order by created_at desc limit 200", (status,) if status else ())
    return rows


def retry_dead_letter(actor: str, entry_id: str) -> dict[str, Any]:
    with _db() as db:
        row = db.one("select * from dead_letters where id = ?", (entry_id,))
    if not row:
        raise AdminError("not_found", 404)
    payload = json.loads(row["payload"])
    status, error = "resolved", ""
    try:
        if row["kind"] == "billing_webhook":
            billing.process_webhook(row["source"], payload.get("headers") or {}, (payload.get("body") or "").encode("utf-8"))
        else:
            raise AdminError("not_retryable", 409)
    except AdminError:
        raise
    except Exception as caught:  # noqa: BLE001
        status, error = "failed", f"{type(caught).__name__}: {caught}"[:500]
    with _db() as db:
        db.run("update dead_letters set attempts = attempts + 1, status = ?, error = case when ? = '' then error else ? end, updated_at = ? where id = ?", (status, error, error, now_iso(), entry_id))
    audit(actor, "job.retry", entry_id, {"kind": row["kind"], "result": status})
    return {"id": entry_id, "status": status, "error": error or None}


def discard_dead_letter(actor: str, entry_id: str) -> None:
    with _db() as db:
        db.run("update dead_letters set status = 'discarded', updated_at = ? where id = ?", (now_iso(), entry_id))
    audit(actor, "job.discard", entry_id, {})


# ------------------------------------------------------------------------------------------------ status incidents

def incidents(include_resolved: bool = True, limit: int = 30) -> list[dict[str, Any]]:
    with _db() as db:
        if include_resolved:
            return db.all("select * from status_incidents order by created_at desc limit ?", (limit,))
        return db.all("select * from status_incidents where status != 'resolved' order by created_at desc", ())


def save_incident(actor: str, *, incident_id: str | None, title: str, component: str, severity: str, status: str, message: str) -> dict[str, Any]:
    if component not in COMPONENTS or severity not in SEVERITIES or status not in INCIDENT_STATES or not title.strip():
        raise AdminError("invalid_incident", 422)
    now = now_iso()
    with _db() as db:
        if incident_id:
            current = db.one("select * from status_incidents where id = ?", (incident_id,))
            if not current:
                raise AdminError("not_found", 404)
            db.run("update status_incidents set title=?, component=?, severity=?, status=?, message=?, updated_at=?, resolved_at=? where id=?",
                   (title[:200], component, severity, status, message[:2000], now, now if status == "resolved" else None, incident_id))
        else:
            incident_id = f"inc_{uuid.uuid4().hex[:16]}"
            db.run("insert into status_incidents (id, title, component, severity, status, message, created_at, updated_at, resolved_at) values (?,?,?,?,?,?,?,?,?)",
                   (incident_id, title[:200], component, severity, status, message[:2000], now, now, now if status == "resolved" else None))
        row = db.one("select * from status_incidents where id = ?", (incident_id,))
    audit(actor, "status.incident", incident_id, {"status": status, "severity": severity, "component": component})
    return row or {}
