"""Plans, credit packs and features — the single source of truth for pricing (override with env JSON).

BILLING_PRICES='{"pro": {"usd": {"month": 900, "year": 9000}, "pkr": {"month": 199900, "year": 1999000}}}'
Amounts are in minor units (cents / paisa). Usage limits come from the credit service (CREDIT_PLAN_LIMITS), so the
pricing page and the enforcement can never disagree.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any

from app.services.credits.service import CreditService

CURRENCIES = ("usd", "pkr")
INTERVALS = ("month", "year")

_PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "rank": 0, "checkout": False, "per_seat": False, "min_seats": 1, "max_seats": 1, "trial_days": 0,
        "prices": {"usd": {"month": 0, "year": 0}, "pkr": {"month": 0, "year": 0}},
        "features": ["search", "reader_basic", "library", "compare_3", "citations", "one_language"],
    },
    "pro": {
        "rank": 1, "checkout": True, "per_seat": False, "min_seats": 1, "max_seats": 1, "trial_days": 7,
        "prices": {"usd": {"month": 900, "year": 9000}, "pkr": {"month": 199900, "year": 1999000}},
        "features": ["everything_free", "research_mode", "reader_full", "compare_unlimited", "gaps_ai", "write_grounded", "exports_all", "priority"],
    },
    "team": {
        "rank": 2, "checkout": True, "per_seat": True, "min_seats": 3, "max_seats": 200, "trial_days": 14,
        "prices": {"usd": {"month": 700, "year": 7000}, "pkr": {"month": 149900, "year": 1499000}},
        "features": ["everything_pro", "shared_projects", "comments_mentions", "supervisor_reviews", "pooled_credits", "team_admin", "audit_log"],
    },
    "institution": {
        "rank": 3, "checkout": False, "per_seat": True, "min_seats": 25, "max_seats": 100000, "trial_days": 0,
        "prices": {"usd": {"month": 0, "year": 0}, "pkr": {"month": 0, "year": 0}},
        "features": ["everything_team", "sso", "invoicing", "data_residency", "dedicated_support"],
    },
}

_PACKS: dict[str, dict[str, Any]] = {
    "credits_100": {"credits": 100, "prices": {"usd": 300, "pkr": 69900}},
    "credits_500": {"credits": 500, "prices": {"usd": 1200, "pkr": 279900}},
    "credits_2000": {"credits": 2000, "prices": {"usd": 4000, "pkr": 899900}},
}


def _override(base: dict[str, Any], env: str) -> dict[str, Any]:
    raw = os.getenv(env)
    if not raw:
        return deepcopy(base)
    try:
        extra = json.loads(raw)
    except ValueError:
        return deepcopy(base)
    merged = deepcopy(base)
    for key, value in (extra or {}).items():
        if key in merged and isinstance(value, dict):
            merged[key] = {**merged[key], **({"prices": {**merged[key].get("prices", {}), **value}} if env == "BILLING_PRICES" else value)}
    return merged


def plans() -> dict[str, dict[str, Any]]:
    data = _override(_PLANS, "BILLING_PRICES")
    for plan_id, plan in data.items():
        plan["id"] = plan_id
        plan["limits"] = CreditService.limits(plan_id)
    return data


def packs() -> dict[str, dict[str, Any]]:
    data = _override(_PACKS, "BILLING_PACKS")
    for pack_id, pack in data.items():
        pack["id"] = pack_id
    return data


def plan(plan_id: str) -> dict[str, Any] | None:
    return plans().get(plan_id)


def price(plan_id: str, currency: str, interval: str, seats: int = 1) -> int:
    info = plan(plan_id)
    if info is None:
        raise KeyError(plan_id)
    unit = int(info["prices"][currency][interval])
    return unit * (seats if info["per_seat"] else 1)
