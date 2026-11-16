"""Subscriptions, checkout, invoices and credit packs (token-based usage on top of plans).

Lifecycle
  free ──checkout──▶ trialing/active ──renewal (period end)──▶ active … ──cancel──▶ cancel_at_period_end ──▶ canceled → free
  upgrades apply immediately with a prorated invoice; downgrades are scheduled for the end of the paid period.
  past_due keeps paid features for a 7-day grace period, then the account falls back to free.

Renewals for the sandbox provider are applied lazily whenever a subscription is read, so no scheduler is needed;
real providers renew through their webhooks (subscription.renewed).

Credits
  Each plan has rolling 5-hour, 7-day and monthly credit windows (app.services.credits). Purchased packs add
  credits that never expire and are spent only after a window is exhausted. Team plans pool credits for all members
  on one team key, with limits multiplied by the number of seats.
"""

from __future__ import annotations

import json
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import settings
from app.services.billing import catalog
from app.services.billing.providers import NormalizedEvent, SandboxProvider, get_provider
from app.services.credits import service as credits
from app.services.sqlstore import database, now_iso

GRACE_DAYS = 7

SCHEMA = [
    """create table if not exists billing_subscriptions (
        id text primary key, owner_id text not null, plan text not null, interval text not null, currency text not null,
        seats integer not null default 1, team_id text, status text not null, provider text not null,
        provider_customer_id text, provider_subscription_id text, current_period_start text not null,
        current_period_end text not null, cancel_at_period_end integer not null default 0, pending_plan text,
        pending_interval text, pending_seats integer, trial_end text, past_due_since text, created_at text not null, updated_at text not null)""",
    "create index if not exists ix_billing_sub_owner on billing_subscriptions (owner_id, status)",
    """create table if not exists billing_checkout_sessions (
        id text primary key, owner_id text not null, kind text not null, plan text, interval text, currency text not null,
        seats integer not null default 1, pack text, team_id text, amount integer not null, status text not null,
        provider text not null, provider_session_id text, url text, created_at text not null, expires_at text not null,
        completed_at text)""",
    """create table if not exists billing_invoices (
        id text primary key, number text not null, owner_id text not null, subscription_id text, kind text not null,
        description text not null, amount integer not null, currency text not null, status text not null,
        period_start text, period_end text, provider_invoice_id text, created_at text not null)""",
    "create index if not exists ix_billing_invoices_owner on billing_invoices (owner_id, created_at)",
    """create table if not exists billing_events (
        event_id text primary key, provider text not null, type text not null, payload text not null, processed_at text not null)""",
    """create table if not exists billing_topups (
        id text primary key, owner_id text not null, credits_total integer not null, credits_used integer not null default 0,
        session_id text, created_at text not null)""",
    "create index if not exists ix_billing_topups_owner on billing_topups (owner_id)",
    """create table if not exists billing_topup_holds (
        reservation_id text primary key, owner_id text not null, topup_id text not null, amount integer not null,
        created_at text not null)""",
]


class BillingError(Exception):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def _db():
    return database("billing", SCHEMA)


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _add_interval(start: datetime, interval: str) -> datetime:
    if interval == "year":
        try:
            return start.replace(year=start.year + 1)
        except ValueError:  # 29 Feb
            return start.replace(year=start.year + 1, day=28)
    month = start.month + 1
    year = start.year + (month > 12)
    month = month - 12 if month > 12 else month
    day = min(start.day, [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return start.replace(year=year, month=month, day=day)


def _invoice_number(db) -> str:  # noqa: ANN001
    count = int(db.scalar("select count(*) from billing_invoices") or 0)
    return f"RS-{datetime.now(UTC):%Y%m}-{count + 1:05d}"


def _create_invoice(db, *, owner: str, subscription_id: str | None, kind: str, description: str, amount: int, currency: str, period_start: str | None = None, period_end: str | None = None, provider_invoice_id: str | None = None) -> dict[str, Any]:  # noqa: ANN001
    invoice = {
        "id": f"inv_{uuid.uuid4().hex[:16]}", "number": _invoice_number(db), "owner_id": owner, "subscription_id": subscription_id, "kind": kind,
        "description": description, "amount": int(amount), "currency": currency, "status": "paid", "period_start": period_start,
        "period_end": period_end, "provider_invoice_id": provider_invoice_id, "created_at": now_iso(),
    }
    db.run(
        "insert into billing_invoices (id, number, owner_id, subscription_id, kind, description, amount, currency, status, period_start, period_end, provider_invoice_id, created_at) values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        tuple(invoice.values()),
    )
    return invoice


# ------------------------------------------------------------------------------------------------- subscriptions


def _live_subscription(db, owner: str) -> dict[str, Any] | None:  # noqa: ANN001
    return db.one("select * from billing_subscriptions where owner_id = ? and status in ('active','trialing','past_due') order by created_at desc limit 1", (owner,))


def _refresh(db, sub: dict[str, Any], now: datetime | None = None) -> dict[str, Any] | None:  # noqa: ANN001
    """Apply renewals, scheduled downgrades, cancellations and grace expiry that are due."""
    now = now or datetime.now(UTC)
    changed = False
    for _ in range(36):  # catch up at most three years of missed periods
        end = _parse(sub["current_period_end"])
        if end is None or end > now:
            break
        if sub["status"] == "past_due":
            break
        if sub["cancel_at_period_end"]:
            sub["status"] = "canceled"
            changed = True
            break
        if sub["provider"] != "sandbox":
            break  # real providers renew via webhooks
        if sub["pending_plan"]:
            sub["plan"], sub["interval"], sub["seats"] = sub["pending_plan"], sub["pending_interval"] or sub["interval"], sub["pending_seats"] or sub["seats"]
            sub["pending_plan"] = sub["pending_interval"] = sub["pending_seats"] = None
        if sub["plan"] == "free":
            sub["status"] = "canceled"
            changed = True
            break
        start, new_end = end, _add_interval(end, sub["interval"])
        amount = catalog.price(sub["plan"], sub["currency"], sub["interval"], sub["seats"])
        _create_invoice(db, owner=sub["owner_id"], subscription_id=sub["id"], kind="renewal", description=f"{sub['plan']} · {sub['interval']}", amount=amount, currency=sub["currency"], period_start=start.isoformat(), period_end=new_end.isoformat())
        sub.update(status="active", current_period_start=start.isoformat(), current_period_end=new_end.isoformat(), trial_end=None)
        changed = True
    if sub["status"] == "past_due" and sub.get("past_due_since"):
        if now - _parse(sub["past_due_since"]) > timedelta(days=GRACE_DAYS):
            sub["status"] = "canceled"
            changed = True
    if changed:
        sub["updated_at"] = now_iso()
        db.run(
            "update billing_subscriptions set plan=?, interval=?, seats=?, status=?, current_period_start=?, current_period_end=?, pending_plan=?, pending_interval=?, pending_seats=?, trial_end=?, updated_at=? where id=?",
            (sub["plan"], sub["interval"], sub["seats"], sub["status"], sub["current_period_start"], sub["current_period_end"], sub["pending_plan"], sub["pending_interval"], sub["pending_seats"], sub["trial_end"], sub["updated_at"], sub["id"]),
        )
    return sub if sub["status"] in ("active", "trialing", "past_due") else None


def subscription(owner: str) -> dict[str, Any] | None:
    with _db() as db:
        sub = _live_subscription(db, owner)
        return _refresh(db, sub) if sub else None


def effective_plan(owner: str) -> tuple[str, str | None, int]:
    """(plan, team_id, seats) that applies to this person right now: own subscription or a team they belong to."""
    best = ("free", None, 1)
    own = subscription(owner)
    if own:
        best = (own["plan"], own.get("team_id"), int(own["seats"] or 1))
    try:
        from app.services.teams.store import teams_for_member
    except ImportError:  # pragma: no cover
        return best
    for team in teams_for_member(owner):
        team_sub = subscription(team["owner_id"])
        if team_sub and team_sub.get("team_id") == team["id"] and catalog.plan(team_sub["plan"])["rank"] > catalog.plan(best[0])["rank"]:
            best = (team_sub["plan"], team["id"], int(team_sub["seats"] or 1))
    return best


def _start_subscription(db, *, owner: str, plan: str, interval: str, currency: str, seats: int, team_id: str | None, provider: str, provider_subscription_id: str | None, provider_customer_id: str | None, amount: int, trial_days: int) -> dict[str, Any]:  # noqa: ANN001
    now = datetime.now(UTC)
    current = _live_subscription(db, owner)
    if current:  # replacing a plan: the old one ends now
        db.run("update billing_subscriptions set status='canceled', updated_at=? where id=?", (now_iso(), current["id"]))
    trial_end = now + timedelta(days=trial_days) if trial_days and not db.one("select id from billing_subscriptions where owner_id = ? and plan = ?", (owner, plan)) else None
    end = trial_end or _add_interval(now, interval)
    sub = {
        "id": f"sub_{uuid.uuid4().hex[:16]}", "owner_id": owner, "plan": plan, "interval": interval, "currency": currency, "seats": seats, "team_id": team_id,
        "status": "trialing" if trial_end else "active", "provider": provider, "provider_customer_id": provider_customer_id,
        "provider_subscription_id": provider_subscription_id, "current_period_start": now.isoformat(), "current_period_end": end.isoformat(),
        "cancel_at_period_end": 0, "pending_plan": None, "pending_interval": None, "pending_seats": None,
        "trial_end": trial_end.isoformat() if trial_end else None, "past_due_since": None, "created_at": now_iso(), "updated_at": now_iso(),
    }
    db.run(f"insert into billing_subscriptions ({','.join(sub)}) values ({','.join('?' for _ in sub)})", tuple(sub.values()))
    if not trial_end:
        _create_invoice(db, owner=owner, subscription_id=sub["id"], kind="subscription", description=f"{plan} · {interval}" + (f" · {seats} seats" if seats > 1 else ""), amount=amount, currency=currency, period_start=sub["current_period_start"], period_end=sub["current_period_end"])
    return sub


# ------------------------------------------------------------------------------------------------- checkout


def create_checkout(owner: str, *, kind: str, plan: str | None, interval: str, currency: str, seats: int, pack: str | None, team_id: str | None, customer_email: str | None, return_base: str) -> dict[str, Any]:
    if currency not in catalog.CURRENCIES or interval not in catalog.INTERVALS:
        raise BillingError("invalid_option")
    if kind == "subscription":
        info = catalog.plan(plan or "")
        if not info or not info["checkout"]:
            raise BillingError("plan_not_purchasable")
        seats = max(info["min_seats"], min(int(seats or 1), info["max_seats"])) if info["per_seat"] else 1
        if info["per_seat"] and not team_id:
            raise BillingError("team_required")
        if team_id:
            from app.services.teams.store import role_of

            if role_of(team_id, owner) != "owner":
                raise BillingError("forbidden", 403)
        current = subscription(owner)
        if current and current["plan"] == plan and current["interval"] == interval and int(current["seats"]) == seats:
            raise BillingError("already_on_plan", 409)
        amount = catalog.price(plan, currency, interval, seats)
    elif kind == "topup":
        info = catalog.packs().get(pack or "")
        if not info:
            raise BillingError("invalid_pack")
        amount, plan, seats = int(info["prices"][currency]), None, 1
    else:
        raise BillingError("invalid_option")
    provider = get_provider()
    now = datetime.now(UTC)
    session = {
        "id": f"cs_{uuid.uuid4().hex[:20]}", "owner_id": owner, "kind": kind, "plan": plan, "interval": interval, "currency": currency,
        "seats": seats, "pack": pack, "team_id": team_id, "amount": amount, "status": "open", "provider": provider.name,
        "provider_session_id": None, "url": None, "created_at": now.isoformat(), "expires_at": (now + timedelta(hours=1)).isoformat(), "completed_at": None,
    }
    created = provider.create_checkout(session, success_url=f"{return_base}/usage?checkout=success", cancel_url=f"{return_base}/pricing?checkout=canceled", customer_email=customer_email)
    session.update(provider_session_id=created["provider_session_id"], url=created["url"])
    with _db() as db:
        db.run(f"insert into billing_checkout_sessions ({','.join(session)}) values ({','.join('?' for _ in session)})", tuple(session.values()))
    return session


def checkout_session(owner: str, session_id: str) -> dict[str, Any]:
    with _db() as db:
        session = db.one("select * from billing_checkout_sessions where id = ? and owner_id = ?", (session_id, owner))
        if not session:
            raise BillingError("not_found", 404)
        if session["status"] == "open" and _parse(session["expires_at"]) < datetime.now(UTC):
            db.run("update billing_checkout_sessions set status='expired' where id=?", (session_id,))
            session["status"] = "expired"
        return session


def sandbox_complete(owner: str, session_id: str, *, approve: bool) -> dict[str, Any]:
    """The sandbox 'payment page' result, delivered as a signed webhook through the normal processing path."""
    provider = get_provider()
    if not provider.sandbox or settings.deployment_stage.lower() == "production":
        raise BillingError("sandbox_disabled", 403)
    session = checkout_session(owner, session_id)
    if session["status"] != "open":
        raise BillingError(f"session_{session['status']}", 409)
    if not approve:
        with _db() as db:
            db.run("update billing_checkout_sessions set status='canceled' where id=?", (session_id,))
        return {**session, "status": "canceled"}
    body = json.dumps({"id": f"evt_{uuid.uuid4().hex}", "type": "checkout.completed", "data": {"session_id": session_id, "provider_subscription_id": f"sbx_sub_{uuid.uuid4().hex[:10]}" if session["kind"] == "subscription" else None, "provider_customer_id": f"sbx_cus_{owner[:24]}"}}).encode()
    process_webhook("sandbox", {"x-resora-signature": SandboxProvider.sign(body)}, body)
    return checkout_session(owner, session_id)


def process_webhook(provider_name: str, headers: dict[str, str], body: bytes) -> int:
    """Verify, deduplicate and apply provider events. Returns how many new events were applied."""
    provider = get_provider(provider_name)
    if provider.name != provider_name:
        raise BillingError("unknown_provider", 404)
    events = provider.verify_and_parse({key.lower(): value for key, value in headers.items()}, body)
    applied = 0
    for event in events:
        with _db() as db:
            if db.one("select event_id from billing_events where event_id = ?", (event.event_id,)):
                continue
            _apply(db, provider_name, event)
            db.run("insert into billing_events (event_id, provider, type, payload, processed_at) values (?,?,?,?,?)", (event.event_id, provider_name, event.type, json.dumps(event.data), now_iso()))
            applied += 1
    return applied


def _apply(db, provider_name: str, event: NormalizedEvent) -> None:  # noqa: ANN001
    data = event.data
    if event.type == "checkout.completed":
        session = db.one("select * from billing_checkout_sessions where id = ?", (data.get("session_id"),))
        if not session or session["status"] == "completed":
            return
        db.run("update billing_checkout_sessions set status='completed', completed_at=? where id=?", (now_iso(), session["id"]))
        if session["kind"] == "topup":
            pack = catalog.packs()[session["pack"]]
            db.run("insert into billing_topups (id, owner_id, credits_total, credits_used, session_id, created_at) values (?,?,?,?,?,?)", (f"top_{uuid.uuid4().hex[:16]}", session["owner_id"], int(pack["credits"]), 0, session["id"], now_iso()))
            _create_invoice(db, owner=session["owner_id"], subscription_id=None, kind="topup", description=f"{pack['credits']} credits", amount=session["amount"], currency=session["currency"])
        else:
            info = catalog.plan(session["plan"])
            _start_subscription(
                db, owner=session["owner_id"], plan=session["plan"], interval=session["interval"], currency=session["currency"], seats=int(session["seats"]),
                team_id=session["team_id"], provider=provider_name, provider_subscription_id=data.get("provider_subscription_id"),
                provider_customer_id=data.get("provider_customer_id"), amount=session["amount"], trial_days=int(info["trial_days"]),
            )
        return
    sub = db.one("select * from billing_subscriptions where provider_subscription_id = ? order by created_at desc limit 1", (data.get("provider_subscription_id"),)) if data.get("provider_subscription_id") else None
    if event.type == "subscription.renewed" and sub:
        start = _parse(sub["current_period_end"]) or datetime.now(UTC)
        end = datetime.fromtimestamp(int(data["period_end"]), tz=UTC) if data.get("period_end") else _add_interval(start, sub["interval"])
        db.run("update billing_subscriptions set status='active', past_due_since=null, current_period_start=?, current_period_end=?, updated_at=? where id=?", (start.isoformat(), end.isoformat(), now_iso(), sub["id"]))
        _create_invoice(db, owner=sub["owner_id"], subscription_id=sub["id"], kind="renewal", description=f"{sub['plan']} · {sub['interval']}", amount=catalog.price(sub["plan"], sub["currency"], sub["interval"], int(sub["seats"])), currency=sub["currency"], period_start=start.isoformat(), period_end=end.isoformat())
    elif event.type == "subscription.past_due" and sub:
        db.run("update billing_subscriptions set status='past_due', past_due_since=?, updated_at=? where id=?", (now_iso(), now_iso(), sub["id"]))
    elif event.type == "subscription.canceled" and sub:
        db.run("update billing_subscriptions set status='canceled', updated_at=? where id=?", (now_iso(), sub["id"]))
    elif event.type == "payment.refunded":
        db.run("update billing_invoices set status='refunded' where provider_invoice_id = ?", (data.get("provider_invoice_id"),))


# ------------------------------------------------------------------------------------------------- self-service changes


def change_plan(owner: str, *, plan: str, interval: str, seats: int) -> dict[str, Any]:
    """Upgrade now (prorated invoice for the rest of the period) or schedule a downgrade for the period end."""
    with _db() as db:
        sub = _live_subscription(db, owner)
        sub = _refresh(db, sub) if sub else None
        if not sub:
            raise BillingError("no_subscription", 404)
        target = catalog.plan(plan)
        current = catalog.plan(sub["plan"])
        if not target or (plan != "free" and not target["checkout"]):
            raise BillingError("plan_not_purchasable")
        seats = max(target["min_seats"], min(int(seats or 1), target["max_seats"])) if target["per_seat"] else 1
        if target["per_seat"] and not sub.get("team_id"):
            raise BillingError("team_required")
        new_price = catalog.price(plan, sub["currency"], interval, seats) if plan != "free" else 0
        old_price = catalog.price(sub["plan"], sub["currency"], sub["interval"], int(sub["seats"]))
        now = datetime.now(UTC)
        start, end = _parse(sub["current_period_start"]), _parse(sub["current_period_end"])
        is_upgrade = target["rank"] > current["rank"] or (target["rank"] == current["rank"] and new_price > old_price and interval == sub["interval"])
        if is_upgrade and sub["status"] != "trialing":
            remaining = max(0.0, (end - now).total_seconds() / max(1.0, (end - start).total_seconds()))
            prorated = max(0, round((new_price - old_price) * remaining)) if interval == sub["interval"] else new_price
            new_end = end if interval == sub["interval"] else _add_interval(now, interval)
            db.run("update billing_subscriptions set plan=?, interval=?, seats=?, current_period_end=?, pending_plan=null, pending_interval=null, pending_seats=null, cancel_at_period_end=0, updated_at=? where id=?", (plan, interval, seats, new_end.isoformat(), now_iso(), sub["id"]))
            if prorated:
                _create_invoice(db, owner=owner, subscription_id=sub["id"], kind="proration", description=f"{sub['plan']} → {plan}", amount=prorated, currency=sub["currency"], period_start=now.isoformat(), period_end=new_end.isoformat())
            return {"applied": "now", "prorated_amount": prorated, "currency": sub["currency"]}
        if sub["status"] == "trialing":
            db.run("update billing_subscriptions set plan=?, interval=?, seats=?, updated_at=? where id=?", (plan, interval, seats, now_iso(), sub["id"]))
            return {"applied": "now", "prorated_amount": 0, "currency": sub["currency"]}
        db.run("update billing_subscriptions set pending_plan=?, pending_interval=?, pending_seats=?, updated_at=? where id=?", (plan, interval, seats, now_iso(), sub["id"]))
        return {"applied": "period_end", "effective_at": sub["current_period_end"], "prorated_amount": 0, "currency": sub["currency"]}


def set_cancel(owner: str, *, cancel: bool) -> dict[str, Any]:
    with _db() as db:
        sub = _live_subscription(db, owner)
        if not sub:
            raise BillingError("no_subscription", 404)
        db.run("update billing_subscriptions set cancel_at_period_end=?, pending_plan=null, pending_interval=null, pending_seats=null, updated_at=? where id=?", (1 if cancel else 0, now_iso(), sub["id"]))
    if sub["provider_subscription_id"] and sub["provider"] != "sandbox":
        get_provider(sub["provider"]).cancel_subscription(sub["provider_subscription_id"], at_period_end=cancel)
    return subscription(owner) or {}


def invoices(owner: str) -> list[dict[str, Any]]:
    with _db() as db:
        return db.all("select * from billing_invoices where owner_id = ? order by created_at desc limit 100", (owner,))


def invoice(owner: str, invoice_id: str) -> dict[str, Any]:
    with _db() as db:
        row = db.one("select * from billing_invoices where id = ? and owner_id = ?", (invoice_id, owner))
    if not row:
        raise BillingError("not_found", 404)
    return row


# ------------------------------------------------------------------------------------------------- credit packs


def topup_balance(owner: str) -> int:
    with _db() as db:
        return int(db.scalar("select coalesce(sum(credits_total - credits_used), 0) from billing_topups where owner_id = ?", (owner,)) or 0)


def grant_credits(owner: str, credits_amount: int, *, source: str) -> dict[str, Any]:
    """Credits given without payment (admin grant, referral reward). Same never-expiring balance as a credit pack."""
    grant = {"id": f"top_{uuid.uuid4().hex[:16]}", "owner_id": owner, "credits_total": int(credits_amount), "credits_used": 0, "session_id": f"grant:{source}"[:200], "created_at": now_iso()}
    with _db() as db:
        db.run("insert into billing_topups (id, owner_id, credits_total, credits_used, session_id, created_at) values (?,?,?,?,?,?)", tuple(grant.values()))
    return grant


def _owner_from_key(user_key: str) -> str | None:
    return user_key.split(":", 1)[1] if user_key.startswith("user:") else None


class _TopupHooks:
    def balance(self, user_key: str) -> int:
        owner = _owner_from_key(user_key)
        return topup_balance(owner) if owner else 0

    def consume(self, user_key: str, amount: int, reservation_id: str) -> bool:
        owner = _owner_from_key(user_key)
        if not owner or amount <= 0:
            return False
        with _db() as db:
            packs = db.all("select id, credits_total, credits_used from billing_topups where owner_id = ? and credits_used < credits_total order by created_at", (owner,))
            if sum(p["credits_total"] - p["credits_used"] for p in packs) < amount:
                return False
            remaining = amount
            for pack in packs:  # oldest pack first
                take = min(remaining, pack["credits_total"] - pack["credits_used"])
                db.run("update billing_topups set credits_used = credits_used + ? where id = ?", (take, pack["id"]))
                db.run("insert into billing_topup_holds (reservation_id, owner_id, topup_id, amount, created_at) values (?,?,?,?,?)", (f"{reservation_id}:{pack['id']}", owner, pack["id"], take, now_iso()))
                remaining -= take
                if remaining == 0:
                    break
        return True

    def adjust(self, reservation_id: str, final_amount: int) -> None:
        with _db() as db:
            holds = db.all("select reservation_id, topup_id, amount from billing_topup_holds where reservation_id like ?", (f"{reservation_id}:%",))
            if not holds:
                return
            excess = sum(hold["amount"] for hold in holds) - max(0, final_amount)
            for hold in reversed(holds):  # give back to the newest pack first
                if excess <= 0:
                    break
                back = min(excess, hold["amount"])
                db.run("update billing_topups set credits_used = credits_used - ? where id = ?", (back, hold["topup_id"]))
                db.run("update billing_topup_holds set amount = amount - ? where reservation_id = ?", (back, hold["reservation_id"]))
                excess -= back


def _resolver(user_key: str, plan: str) -> tuple[str, str, int]:
    owner = _owner_from_key(user_key)
    if not owner:
        return plan, user_key, 1
    effective, team_id, seats = effective_plan(owner)
    if team_id and catalog.plan(effective) and catalog.plan(effective)["per_seat"]:
        return effective, f"team:{team_id}", seats  # pooled credits for the whole team
    return (effective if catalog.plan(effective)["rank"] >= (catalog.plan(plan) or {"rank": 0})["rank"] else plan), user_key, 1


def install() -> None:
    """Register billing with the credit service (idempotent; called when the billing router is imported)."""
    credits.set_plan_resolver(_resolver)
    credits.set_topup_hooks(_TopupHooks())


def usage_for(owner: str, credit_key: str) -> dict[str, Any]:
    plan, team_id, seats = effective_plan(owner)
    usage = credits.get_credit_service().usage(credit_key, plan)
    history = credits.get_credit_service().history(credit_key, time.time() - 30 * 86400, plan)
    sub = subscription(owner)
    return {
        "plan": plan, "team_id": team_id, "seats": seats, "subscription": sub, "usage": usage, "history": history,
        "topup_balance": topup_balance(owner), "provider": get_provider().name, "sandbox": get_provider().sandbox,
        "costs": {action: credits.CreditService.cost(action) for action in credits.DEFAULT_ACTION_COSTS},
    }


def new_invoice_token() -> str:
    return secrets.token_urlsafe(16)
