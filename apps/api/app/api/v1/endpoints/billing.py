"""Plans, subscriptions, credit packs, usage, invoices and payment webhooks."""

from __future__ import annotations

import asyncio
import html

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.api.deps import AuthContext, get_auth_context
from app.core.config import settings
from app.services.billing import catalog
from app.services.billing import service as billing
from app.services.billing.providers import WebhookError, get_provider

router = APIRouter()
billing.install()


class CheckoutRequest(BaseModel):
    kind: str = Field(pattern="^(subscription|topup)$")
    plan: str | None = None
    interval: str = Field(default="month", pattern="^(month|year)$")
    currency: str = Field(default="usd", pattern="^(usd|pkr)$")
    seats: int = Field(default=1, ge=1, le=100000)
    pack: str | None = None
    team_id: str | None = None
    email: str | None = Field(default=None, max_length=254)


class ChangeRequest(BaseModel):
    plan: str
    interval: str = Field(default="month", pattern="^(month|year)$")
    seats: int = Field(default=1, ge=1, le=100000)


def _owner(auth: AuthContext) -> str:
    if (settings.deployment_stage.lower() == "production" and not auth.verified) or not auth.user_id or auth.user_id == "anonymous":
        raise HTTPException(status_code=401, detail={"code": "sign_in_required"})
    return auth.user_id


def _credit_key(auth: AuthContext, request: Request) -> str:
    """Same key the credit-charging endpoints use (signed-in account, otherwise the network address)."""
    if auth.verified and auth.user_id:
        return f"user:{auth.user_id}"
    return f"guest:{request.client.host if request.client else 'unknown'}"


def _guard(call):
    try:
        return call()
    except billing.BillingError as error:
        raise HTTPException(status_code=error.status, detail={"code": error.code}) from error


@router.get("/plans")
async def plans() -> dict:
    provider = get_provider()
    return {"plans": list(catalog.plans().values()), "packs": list(catalog.packs().values()), "currencies": list(catalog.CURRENCIES), "provider": provider.name, "sandbox": provider.sandbox}


@router.get("/me")
async def me(request: Request, auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    return await asyncio.to_thread(billing.usage_for, owner, _credit_key(auth, request))


@router.post("/checkout")
async def checkout(payload: CheckoutRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    origin = request.headers.get("origin") or str(request.base_url).rstrip("/")
    session = await asyncio.to_thread(lambda: _guard(lambda: billing.create_checkout(owner, kind=payload.kind, plan=payload.plan, interval=payload.interval, currency=payload.currency, seats=payload.seats, pack=payload.pack, team_id=payload.team_id, customer_email=payload.email, return_base=origin)))
    return {"session_id": session["id"], "url": session["url"], "amount": session["amount"], "currency": session["currency"]}


@router.get("/checkout/{session_id}")
async def checkout_session(session_id: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    return await asyncio.to_thread(lambda: _guard(lambda: billing.checkout_session(owner, session_id)))


@router.post("/sandbox/{session_id}/{decision}")
async def sandbox(session_id: str, decision: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    if decision not in ("complete", "cancel"):
        raise HTTPException(status_code=404, detail={"code": "not_found"})
    return await asyncio.to_thread(lambda: _guard(lambda: billing.sandbox_complete(owner, session_id, approve=decision == "complete")))


@router.post("/subscription/change")
async def change(payload: ChangeRequest, auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    return await asyncio.to_thread(lambda: _guard(lambda: billing.change_plan(owner, plan=payload.plan, interval=payload.interval, seats=payload.seats)))


@router.post("/subscription/cancel")
async def cancel(auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    return await asyncio.to_thread(lambda: _guard(lambda: billing.set_cancel(owner, cancel=True)))


@router.post("/subscription/resume")
async def resume(auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    return await asyncio.to_thread(lambda: _guard(lambda: billing.set_cancel(owner, cancel=False)))


@router.get("/invoices")
async def invoices(auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    return {"invoices": await asyncio.to_thread(billing.invoices, owner)}


def _money(amount: int, currency: str) -> str:
    symbol = {"usd": "$", "pkr": "Rs "}.get(currency, "")
    return f"{symbol}{amount / 100:,.2f}"


@router.get("/invoices/{invoice_id}/document", response_class=HTMLResponse)
async def invoice_document(invoice_id: str, auth: AuthContext = Depends(get_auth_context)) -> HTMLResponse:
    """A printable invoice (browser 'Save as PDF')."""
    owner = _owner(auth)
    row = await asyncio.to_thread(lambda: _guard(lambda: billing.invoice(owner, invoice_id)))
    esc = html.escape
    period = f"{esc((row['period_start'] or '')[:10])} – {esc((row['period_end'] or '')[:10])}" if row["period_start"] else ""
    body = f"""<!doctype html><html><head><meta charset="utf-8"><title>Invoice {esc(row['number'])}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:720px;margin:40px auto;color:#1c1c1c}}h1{{font-size:22px}}table{{width:100%;border-collapse:collapse;margin-top:24px}}
td,th{{padding:10px;border-bottom:1px solid #ddd;text-align:left}}.total{{font-weight:700}}.muted{{color:#666}}</style></head><body>
<h1>Resora — Invoice {esc(row['number'])}</h1><p class="muted">Issued {esc(row['created_at'][:10])} · Status: {esc(row['status'])}</p>
<p>Account: {esc(owner)}</p><table><tr><th>Description</th><th>Period</th><th>Amount</th></tr>
<tr><td>{esc(row['description'])}</td><td>{period}</td><td>{_money(int(row['amount']), row['currency'])}</td></tr>
<tr class="total"><td colspan="2">Total</td><td>{_money(int(row['amount']), row['currency'])}</td></tr></table></body></html>"""
    return HTMLResponse(body)


@router.post("/webhooks/{provider}")
async def webhook(provider: str, request: Request) -> dict:
    body = await request.body()
    try:
        applied = await asyncio.to_thread(billing.process_webhook, provider, dict(request.headers), body)
    except WebhookError as error:
        raise HTTPException(status_code=400, detail={"code": "invalid_signature"}) from error
    except billing.BillingError as error:
        raise HTTPException(status_code=error.status, detail={"code": error.code}) from error
    except Exception as error:  # noqa: BLE001 - keep the event for a retry from the admin console (Jobs)
        from app.services.admin import service as admin

        keep = {key: value for key, value in request.headers.items() if key.lower() not in {"authorization", "cookie"}}
        await asyncio.to_thread(admin.record_dead_letter, "billing_webhook", provider, {"headers": keep, "body": body.decode("utf-8", "replace")}, f"{type(error).__name__}: {error}")
        raise HTTPException(status_code=500, detail={"code": "webhook_failed"}) from error
    return {"received": True, "applied": applied}
