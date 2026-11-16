"""Growth and the public website: referral credits, newsletter / waitlist, contact messages, cookieless analytics and
the public status page.

Privacy
  * Analytics store no cookies, no IP address and no user id. A visitor is counted with a daily-rotating salted
    hash of (network address, user agent); the salt changes every UTC day and is never stored with the hash's
    inputs, so visits cannot be linked across days (same approach as privacy-first analytics tools).
  * Newsletter sign-up needs explicit consent and is double opt-in: the address is "pending" until the token in the
    confirmation link is used. Unsubscribing is one click and removes the address.
  * Contact messages are kept for the support team only and can be closed or deleted by an admin.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from app.services.billing import service as billing
from app.services.sqlstore import database, now_iso

SCHEMA = [
    """create table if not exists referral_codes (
        user_id text primary key, code text not null unique, created_at text not null)""",
    """create table if not exists referral_redemptions (
        referee_id text primary key, referrer_id text not null, code text not null, rewarded integer not null default 0,
        created_at text not null)""",
    "create index if not exists ix_referral_referrer on referral_redemptions (referrer_id)",
    """create table if not exists newsletter_subscribers (
        email text primary key, status text not null, language text not null, source text not null, token text not null,
        consent_at text not null, confirmed_at text, created_at text not null)""",
    """create table if not exists contact_messages (
        id text primary key, name text not null, email text not null, topic text not null, message text not null,
        language text not null, status text not null, user_id text, created_at text not null, updated_at text not null)""",
    """create table if not exists pageviews (
        day text not null, path text not null, referrer text not null, language text not null, visitor text not null,
        device text not null, created_at text not null)""",
    "create index if not exists ix_pageviews_day on pageviews (day)",
]

EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")
TOPICS = ("general", "support", "billing", "sales", "privacy", "press", "bug")
REFERRAL_CREDITS = int(os.getenv("REFERRAL_CREDITS", "50") or 50)
REFERRAL_MAX_REWARDS = int(os.getenv("REFERRAL_MAX_REWARDS", "20") or 20)
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I


class GrowthError(Exception):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def _db():
    return database("growth", SCHEMA)


# ------------------------------------------------------------------------------------------------ referrals

def referral(user_id: str) -> dict[str, Any]:
    with _db() as db:
        row = db.one("select code from referral_codes where user_id = ?", (user_id,))
        if not row:
            for _ in range(8):
                code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
                if not db.one("select code from referral_codes where code = ?", (code,)):
                    db.run("insert into referral_codes (user_id, code, created_at) values (?,?,?)", (user_id, code, now_iso()))
                    row = {"code": code}
                    break
        invited = int(db.scalar("select count(*) from referral_redemptions where referrer_id = ?", (user_id,)) or 0)
        rewarded = int(db.scalar("select count(*) from referral_redemptions where referrer_id = ? and rewarded = 1", (user_id,)) or 0)
        redeemed = db.one("select code from referral_redemptions where referee_id = ?", (user_id,))
    return {"code": row["code"], "invited": invited, "rewarded": rewarded, "credits_earned": rewarded * REFERRAL_CREDITS,
            "credits_per_referral": REFERRAL_CREDITS, "max_rewards": REFERRAL_MAX_REWARDS, "redeemed_code": redeemed["code"] if redeemed else None}


def redeem(user_id: str, code: str) -> dict[str, Any]:
    """Both people get REFERRAL_CREDITS. One redemption per account; referrers are rewarded up to a cap."""
    code = code.strip().upper()
    with _db() as db:
        owner = db.one("select user_id from referral_codes where code = ?", (code,))
        if not owner:
            raise GrowthError("referral_invalid", 404)
        if owner["user_id"] == user_id:
            raise GrowthError("referral_self", 409)
        if db.one("select referee_id from referral_redemptions where referee_id = ?", (user_id,)):
            raise GrowthError("referral_used", 409)
        if db.one("select referee_id from referral_redemptions where referee_id = ? and referrer_id = ?", (owner["user_id"], user_id)):
            raise GrowthError("referral_circular", 409)
        rewarded = int(db.scalar("select count(*) from referral_redemptions where referrer_id = ? and rewarded = 1", (owner["user_id"],)) or 0)
        reward_referrer = rewarded < REFERRAL_MAX_REWARDS
        db.run("insert into referral_redemptions (referee_id, referrer_id, code, rewarded, created_at) values (?,?,?,?,?)", (user_id, owner["user_id"], code, int(reward_referrer), now_iso()))
    billing.grant_credits(user_id, REFERRAL_CREDITS, source=f"referral:{code}")
    if reward_referrer:
        billing.grant_credits(owner["user_id"], REFERRAL_CREDITS, source=f"referral-reward:{user_id}")
    return {"credits": REFERRAL_CREDITS, "balance": billing.topup_balance(user_id)}


def referral_summary() -> dict[str, int]:
    with _db() as db:
        return {"redemptions": int(db.scalar("select count(*) from referral_redemptions") or 0),
                "codes": int(db.scalar("select count(*) from referral_codes") or 0)}


# ------------------------------------------------------------------------------------------------ newsletter / waitlist

def subscribe(email: str, *, consent: bool, language: str, source: str) -> dict[str, Any]:
    email = email.strip().lower()
    if not EMAIL.match(email):
        raise GrowthError("invalid_email", 422)
    if not consent:
        raise GrowthError("consent_required", 422)
    token = secrets.token_urlsafe(24)
    with _db() as db:
        row = db.one("select status from newsletter_subscribers where email = ?", (email,))
        if row and row["status"] == "confirmed":
            return {"status": "confirmed"}  # never reveal more than that
        db.run("delete from newsletter_subscribers where email = ?", (email,))
        db.run("insert into newsletter_subscribers (email, status, language, source, token, consent_at, confirmed_at, created_at) values (?,?,?,?,?,?,?,?)",
               (email, "pending", language[:16], source[:40], hashlib.sha256(token.encode()).hexdigest(), now_iso(), None, now_iso()))
    # The confirmation e-mail is sent by the configured mailer (SMTP_*). Without one, the token is only logged as
    # "pending" and an admin can export confirmed addresses only.
    _send_confirmation(email, token, language)
    return {"status": "pending"}


def _send_confirmation(email: str, token: str, language: str) -> None:
    host = os.getenv("SMTP_HOST", "")
    if not host:
        return
    import smtplib
    from email.message import EmailMessage

    base = os.getenv("PUBLIC_SITE_URL", "http://localhost:5173").rstrip("/")
    message = EmailMessage()
    message["Subject"] = "Confirm your Resora subscription"
    message["From"] = os.getenv("SMTP_FROM", "Resora <no-reply@example.com>")
    message["To"] = email
    message.set_content(f"Confirm your subscription to Resora updates:\n{base}/newsletter/confirm?token={token}\n\nIf you did not ask for this, ignore this e-mail.")
    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=10) as smtp:
            if os.getenv("SMTP_STARTTLS", "1") == "1":
                smtp.starttls()
            if os.getenv("SMTP_USERNAME"):
                smtp.login(os.getenv("SMTP_USERNAME", ""), os.getenv("SMTP_PASSWORD", ""))
            smtp.send_message(message)
    except Exception:  # noqa: BLE001 - sign-up must not fail because the mailer is down
        return


def confirm(token: str) -> dict[str, str]:
    digest = hashlib.sha256(token.encode()).hexdigest()
    with _db() as db:
        row = db.one("select email from newsletter_subscribers where token = ?", (digest,))
        if not row:
            raise GrowthError("token_invalid", 404)
        db.run("update newsletter_subscribers set status = 'confirmed', confirmed_at = ? where email = ?", (now_iso(), row["email"]))
    return {"status": "confirmed"}


def unsubscribe(token: str) -> dict[str, str]:
    digest = hashlib.sha256(token.encode()).hexdigest()
    with _db() as db:
        db.run("delete from newsletter_subscribers where token = ?", (digest,))
    return {"status": "removed"}


def waitlist_count() -> dict[str, int]:
    with _db() as db:
        rows = db.all("select status, count(*) as n from newsletter_subscribers group by status")
    return {row["status"]: int(row["n"]) for row in rows}


# ------------------------------------------------------------------------------------------------ contact

def contact(*, name: str, email: str, topic: str, message: str, language: str, user_id: str | None) -> dict[str, str]:
    email = email.strip().lower()
    if not EMAIL.match(email):
        raise GrowthError("invalid_email", 422)
    if topic not in TOPICS:
        topic = "general"
    if len(message.strip()) < 10:
        raise GrowthError("message_too_short", 422)
    message_id = f"msg_{uuid.uuid4().hex[:16]}"
    with _db() as db:
        db.run("insert into contact_messages (id, name, email, topic, message, language, status, user_id, created_at, updated_at) values (?,?,?,?,?,?,?,?,?,?)",
               (message_id, name.strip()[:120] or "-", email, topic, message.strip()[:5000], language[:16], "open", user_id, now_iso(), now_iso()))
    return {"id": message_id, "status": "received"}


def contact_messages(status: str | None = None) -> list[dict[str, Any]]:
    with _db() as db:
        if status:
            return db.all("select * from contact_messages where status = ? order by created_at desc limit 200", (status,))
        return db.all("select * from contact_messages order by created_at desc limit 200")


def contact_count(status: str = "open") -> int:
    with _db() as db:
        return int(db.scalar("select count(*) from contact_messages where status = ?", (status,)) or 0)


def set_contact_status(message_id: str, status: str) -> None:
    if status not in ("open", "closed"):
        raise GrowthError("invalid_status", 422)
    with _db() as db:
        db.run("update contact_messages set status = ?, updated_at = ? where id = ?", (status, now_iso(), message_id))


# ------------------------------------------------------------------------------------------------ cookieless analytics

_SALT: dict[str, str] = {}


def _daily_salt(day: str) -> str:
    if day not in _SALT:
        _SALT.clear()  # yesterday's salt is forgotten, so hashes cannot be recomputed
        _SALT[day] = secrets.token_hex(16)
    return _SALT[day]


def _device(user_agent: str) -> str:
    ua = user_agent.lower()
    if "bot" in ua or "spider" in ua or "crawl" in ua:
        return "bot"
    if "mobile" in ua or "iphone" in ua or "android" in ua:
        return "mobile"
    if "ipad" in ua or "tablet" in ua:
        return "tablet"
    return "desktop"


def record_pageview(*, path: str, referrer: str, language: str, client: str, user_agent: str) -> None:
    device = _device(user_agent or "")
    if device == "bot":
        return
    day = datetime.now(UTC).date().isoformat()
    visitor = hashlib.sha256(f"{_daily_salt(day)}|{client}|{user_agent}".encode()).hexdigest()[:20]
    clean_path = "/" + "/".join(part for part in urlparse(path or "/").path.split("/") if part)[:200]
    clean_path = re.sub(r"/[0-9a-f]{8,}|/[A-Za-z0-9_-]{20,}", "/:id", clean_path)  # no ids or tokens in analytics
    host = urlparse(referrer or "").netloc.lower().removeprefix("www.")[:100]
    with _db() as db:
        db.run("insert into pageviews (day, path, referrer, language, visitor, device, created_at) values (?,?,?,?,?,?,?)",
               (day, clean_path, host, (language or "")[:16], visitor, device, now_iso()))


def traffic_summary(days: int = 30) -> dict[str, Any]:
    since = (datetime.now(UTC).date() - timedelta(days=days - 1)).isoformat()
    with _db() as db:
        rows = db.all("select day, path, referrer, language, visitor, device from pageviews where day >= ?", (since,))
    per_day: dict[str, set[str]] = {}
    views: Counter[str] = Counter()
    paths: Counter[str] = Counter()
    referrers: Counter[str] = Counter()
    languages: Counter[str] = Counter()
    devices: Counter[str] = Counter()
    for row in rows:
        per_day.setdefault(row["day"], set()).add(row["visitor"])
        views[row["day"]] += 1
        paths[row["path"]] += 1
        if row["referrer"]:
            referrers[row["referrer"]] += 1
        languages[row["language"] or "-"] += 1
        devices[row["device"]] += 1
    return {
        "pageviews": len(rows), "visitors": sum(len(v) for v in per_day.values()),
        "by_day": [{"day": day, "views": views[day], "visitors": len(per_day[day])} for day in sorted(per_day)],
        "top_paths": [{"path": p, "views": n} for p, n in paths.most_common(10)],
        "top_referrers": [{"referrer": r, "views": n} for r, n in referrers.most_common(10)],
        "languages": dict(languages.most_common(12)), "devices": dict(devices),
    }


# ------------------------------------------------------------------------------------------------ public status

def status() -> dict[str, Any]:
    """Public, non-sensitive health: one state per component plus open and recent incidents."""
    from app.services.admin import service as admin

    components: dict[str, str] = {"search": "operational", "reader": "operational", "listen": "operational", "billing": "operational",
                                  "ai": "operational", "catalog": "operational", "website": "operational"}
    started = time.perf_counter()
    try:
        with _db() as db:
            db.scalar("select 1")
    except Exception:  # noqa: BLE001
        for key in ("search", "reader", "billing", "catalog"):
            components[key] = "major_outage"
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    try:
        from app.services.ai_router import get_default_router

        health = get_default_router().provider_health()
        configured = [item for item in health.values() if item.get("configured")]
        healthy = [item for item in configured if item.get("healthy")]
        if configured and not healthy:
            components["ai"] = "major_outage"
        elif configured and len(healthy) < len(configured):
            components["ai"] = "degraded"
    except Exception:  # noqa: BLE001
        components["ai"] = "degraded"
    open_incidents = admin.incidents(include_resolved=False)
    rank = {"operational": 0, "maintenance": 1, "degraded": 2, "partial_outage": 3, "major_outage": 4}
    for incident in open_incidents:
        state = {"minor": "degraded", "major": "partial_outage", "critical": "major_outage", "maintenance": "maintenance"}[incident["severity"]]
        if rank[state] > rank[components.get(incident["component"], "operational")]:
            components[incident["component"]] = state
    worst = max(components.values(), key=lambda value: rank[value])
    return {"overall": worst, "components": components, "incidents": admin.incidents(include_resolved=True, limit=15), "checked_at": now_iso(), "db_latency_ms": latency_ms}
