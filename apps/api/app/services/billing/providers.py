"""Payment provider adapters behind one interface (master prompt Part 9: provider interface + sandbox adapter).

BILLING_PROVIDER = sandbox (default) | stripe | paddle | lemonsqueezy
Secrets come only from the environment: BILLING_WEBHOOK_SECRET, STRIPE_SECRET_KEY, PADDLE_API_KEY,
LEMONSQUEEZY_API_KEY, LEMONSQUEEZY_STORE_ID, plus provider price ids in BILLING_PROVIDER_PRICES (JSON).

Every provider turns its webhooks into the same normalized events, processed once (idempotent by event id):
    checkout.completed {session_id, provider_subscription_id?, provider_customer_id?}
    subscription.renewed {provider_subscription_id, period_end}
    subscription.past_due / subscription.canceled {provider_subscription_id}
    payment.refunded {provider_invoice_id}

The sandbox provider works with no external account: checkout opens Resora's own confirmation page and completing
it sends a signed webhook through exactly the same verification and processing code as a real provider.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx


class WebhookError(ValueError):
    pass


@dataclass
class NormalizedEvent:
    event_id: str
    type: str
    data: dict[str, Any]


def webhook_secret() -> str:
    secret = os.getenv("BILLING_WEBHOOK_SECRET", "")
    if not secret and os.getenv("BILLING_PROVIDER", "sandbox") == "sandbox":
        secret = "sandbox-local-webhook-secret"  # local development only; production refuses an empty secret
    return secret


def _provider_prices() -> dict[str, str]:
    try:
        return json.loads(os.getenv("BILLING_PROVIDER_PRICES", "{}")) or {}
    except ValueError:
        return {}


class BillingProvider:
    name = "base"
    sandbox = False

    def create_checkout(self, session: dict[str, Any], *, success_url: str, cancel_url: str, customer_email: str | None) -> dict[str, str]:
        raise NotImplementedError

    def verify_and_parse(self, headers: dict[str, str], body: bytes) -> list[NormalizedEvent]:
        raise NotImplementedError

    def cancel_subscription(self, provider_subscription_id: str, *, at_period_end: bool) -> None:
        """Real providers are told to stop renewing; the sandbox needs no call."""


class SandboxProvider(BillingProvider):
    name = "sandbox"
    sandbox = True

    def create_checkout(self, session: dict[str, Any], *, success_url: str, cancel_url: str, customer_email: str | None) -> dict[str, str]:
        return {"provider_session_id": f"sbx_{session['id']}", "url": f"/billing/checkout/{session['id']}"}

    @staticmethod
    def sign(body: bytes, timestamp: int | None = None) -> str:
        stamp = int(timestamp or time.time())
        digest = hmac.new(webhook_secret().encode(), f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
        return f"t={stamp},v1={digest}"

    def verify_and_parse(self, headers: dict[str, str], body: bytes) -> list[NormalizedEvent]:
        _verify_timestamped(headers.get("x-resora-signature", ""), body, webhook_secret(), separator=".")
        payload = json.loads(body)
        return [NormalizedEvent(payload["id"], payload["type"], payload.get("data") or {})]


def _verify_timestamped(header: str, body: bytes, secret: str, *, separator: str, ts_key: str = "t", sig_key: str = "v1", tolerance: int = 300) -> None:
    if not secret:
        raise WebhookError("webhook secret not configured")
    parts = dict(item.split("=", 1) for item in header.split(",") if "=" in item)
    stamp, signature = parts.get(ts_key), parts.get(sig_key)
    if not stamp or not signature or not stamp.isdigit():
        raise WebhookError("missing signature")
    if abs(time.time() - int(stamp)) > tolerance:
        raise WebhookError("stale signature")
    expected = hmac.new(secret.encode(), f"{stamp}{separator}".encode() + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise WebhookError("bad signature")


class StripeProvider(BillingProvider):  # pragma: no cover - needs a Stripe account; signature logic is unit-tested
    name = "stripe"

    def create_checkout(self, session: dict[str, Any], *, success_url: str, cancel_url: str, customer_email: str | None) -> dict[str, str]:
        key = os.getenv("STRIPE_SECRET_KEY", "")
        price_key = session["pack"] if session["kind"] == "topup" else f"{session['plan']}:{session['interval']}:{session['currency']}"
        price_id = _provider_prices().get(price_key)
        if not key or not price_id:
            raise RuntimeError("stripe not configured")
        data = {
            "mode": "payment" if session["kind"] == "topup" else "subscription",
            "success_url": success_url, "cancel_url": cancel_url, "client_reference_id": session["id"],
            "line_items[0][price]": price_id, "line_items[0][quantity]": str(session.get("seats") or 1),
            "metadata[resora_session]": session["id"],
        }
        if customer_email:
            data["customer_email"] = customer_email
        response = httpx.post("https://api.stripe.com/v1/checkout/sessions", data=data, auth=(key, ""), timeout=20)
        response.raise_for_status()
        body = response.json()
        return {"provider_session_id": body["id"], "url": body["url"]}

    def verify_and_parse(self, headers: dict[str, str], body: bytes) -> list[NormalizedEvent]:
        _verify_timestamped(headers.get("stripe-signature", ""), body, webhook_secret(), separator=".")
        event = json.loads(body)
        obj = (event.get("data") or {}).get("object") or {}
        kind = event.get("type")
        if kind == "checkout.session.completed":
            return [NormalizedEvent(event["id"], "checkout.completed", {"session_id": obj.get("client_reference_id"), "provider_subscription_id": obj.get("subscription"), "provider_customer_id": obj.get("customer")})]
        if kind == "invoice.paid" and obj.get("subscription"):
            return [NormalizedEvent(event["id"], "subscription.renewed", {"provider_subscription_id": obj["subscription"], "period_end": (obj.get("lines", {}).get("data") or [{}])[0].get("period", {}).get("end")})]
        if kind == "invoice.payment_failed":
            return [NormalizedEvent(event["id"], "subscription.past_due", {"provider_subscription_id": obj.get("subscription")})]
        if kind == "customer.subscription.deleted":
            return [NormalizedEvent(event["id"], "subscription.canceled", {"provider_subscription_id": obj.get("id")})]
        if kind == "charge.refunded":
            return [NormalizedEvent(event["id"], "payment.refunded", {"provider_invoice_id": obj.get("invoice")})]
        return []

    def cancel_subscription(self, provider_subscription_id: str, *, at_period_end: bool) -> None:
        key = os.getenv("STRIPE_SECRET_KEY", "")
        if key and provider_subscription_id:
            httpx.post(f"https://api.stripe.com/v1/subscriptions/{provider_subscription_id}", data={"cancel_at_period_end": "true" if at_period_end else "false"}, auth=(key, ""), timeout=20).raise_for_status()


class PaddleProvider(BillingProvider):  # pragma: no cover - needs a Paddle account; signature logic is unit-tested
    name = "paddle"

    def create_checkout(self, session: dict[str, Any], *, success_url: str, cancel_url: str, customer_email: str | None) -> dict[str, str]:
        key = os.getenv("PADDLE_API_KEY", "")
        price_key = session["pack"] if session["kind"] == "topup" else f"{session['plan']}:{session['interval']}:{session['currency']}"
        price_id = _provider_prices().get(price_key)
        if not key or not price_id:
            raise RuntimeError("paddle not configured")
        base = "https://sandbox-api.paddle.com" if os.getenv("PADDLE_ENV", "sandbox") == "sandbox" else "https://api.paddle.com"
        response = httpx.post(f"{base}/transactions", json={"items": [{"price_id": price_id, "quantity": session.get("seats") or 1}], "custom_data": {"resora_session": session["id"]}, "checkout": {"url": success_url}}, headers={"Authorization": f"Bearer {key}"}, timeout=20)
        response.raise_for_status()
        data = response.json()["data"]
        return {"provider_session_id": data["id"], "url": data["checkout"]["url"]}

    def verify_and_parse(self, headers: dict[str, str], body: bytes) -> list[NormalizedEvent]:
        _verify_timestamped(headers.get("paddle-signature", "").replace(";", ","), body, webhook_secret(), separator=":", ts_key="ts", sig_key="h1")
        event = json.loads(body)
        data = event.get("data") or {}
        kind = event.get("event_type")
        if kind == "transaction.completed":
            return [NormalizedEvent(event["event_id"], "checkout.completed", {"session_id": (data.get("custom_data") or {}).get("resora_session"), "provider_subscription_id": data.get("subscription_id"), "provider_customer_id": data.get("customer_id")})]
        if kind == "subscription.past_due":
            return [NormalizedEvent(event["event_id"], "subscription.past_due", {"provider_subscription_id": data.get("id")})]
        if kind == "subscription.canceled":
            return [NormalizedEvent(event["event_id"], "subscription.canceled", {"provider_subscription_id": data.get("id")})]
        return []


class LemonSqueezyProvider(BillingProvider):  # pragma: no cover - needs a Lemon Squeezy store; signature logic is unit-tested
    name = "lemonsqueezy"

    def create_checkout(self, session: dict[str, Any], *, success_url: str, cancel_url: str, customer_email: str | None) -> dict[str, str]:
        key, store = os.getenv("LEMONSQUEEZY_API_KEY", ""), os.getenv("LEMONSQUEEZY_STORE_ID", "")
        variant_key = session["pack"] if session["kind"] == "topup" else f"{session['plan']}:{session['interval']}:{session['currency']}"
        variant = _provider_prices().get(variant_key)
        if not key or not store or not variant:
            raise RuntimeError("lemonsqueezy not configured")
        payload = {"data": {"type": "checkouts", "attributes": {"checkout_data": {"custom": {"resora_session": session["id"]}, **({"email": customer_email} if customer_email else {})}, "product_options": {"redirect_url": success_url}},
                            "relationships": {"store": {"data": {"type": "stores", "id": store}}, "variant": {"data": {"type": "variants", "id": variant}}}}}
        response = httpx.post("https://api.lemonsqueezy.com/v1/checkouts", json=payload, headers={"Authorization": f"Bearer {key}", "Accept": "application/vnd.api+json", "Content-Type": "application/vnd.api+json"}, timeout=20)
        response.raise_for_status()
        data = response.json()["data"]
        return {"provider_session_id": data["id"], "url": data["attributes"]["url"]}

    def verify_and_parse(self, headers: dict[str, str], body: bytes) -> list[NormalizedEvent]:
        secret = webhook_secret()
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not secret or not hmac.compare_digest(expected, headers.get("x-signature", "")):
            raise WebhookError("bad signature")
        event = json.loads(body)
        meta = event.get("meta") or {}
        data = event.get("data") or {}
        attributes = data.get("attributes") or {}
        kind = meta.get("event_name")
        event_id = f"{kind}:{data.get('id')}:{attributes.get('updated_at')}"
        session_id = (meta.get("custom_data") or {}).get("resora_session")
        if kind in ("order_created", "subscription_created"):
            return [NormalizedEvent(event_id, "checkout.completed", {"session_id": session_id, "provider_subscription_id": data.get("id") if kind == "subscription_created" else None, "provider_customer_id": str(attributes.get("customer_id") or "")})]
        if kind == "subscription_payment_success":
            return [NormalizedEvent(event_id, "subscription.renewed", {"provider_subscription_id": str(attributes.get("subscription_id") or data.get("id"))})]
        if kind == "subscription_payment_failed":
            return [NormalizedEvent(event_id, "subscription.past_due", {"provider_subscription_id": str(attributes.get("subscription_id") or data.get("id"))})]
        if kind in ("subscription_cancelled", "subscription_expired"):
            return [NormalizedEvent(event_id, "subscription.canceled", {"provider_subscription_id": data.get("id")})]
        return []


PROVIDERS = {"sandbox": SandboxProvider, "stripe": StripeProvider, "paddle": PaddleProvider, "lemonsqueezy": LemonSqueezyProvider}


def get_provider(name: str | None = None) -> BillingProvider:
    return PROVIDERS.get((name or os.getenv("BILLING_PROVIDER", "sandbox")).lower(), SandboxProvider)()
