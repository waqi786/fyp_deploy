"""Public website and growth API: status page, feature flags for the client, newsletter (double opt-in), contact,
cookieless page views and referral credits."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import AuthContext, get_auth_context
from app.core.config import settings
from app.services.admin import service as admin
from app.services.growth import service as growth

router = APIRouter()

# Small per-address rate limits for the public forms (in-process; put a proxy limit in front in production too).
_HITS: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_LIMITS = {"newsletter": (5, 3600), "contact": (5, 3600), "pageview": (120, 60), "redeem": (10, 3600)}


def _limit(request: Request, bucket: str) -> None:
    count, window = _LIMITS[bucket]
    key = (bucket, request.client.host if request.client else "unknown")
    now = time.time()
    hits = _HITS[key]
    while hits and hits[0] < now - window:
        hits.popleft()
    if len(hits) >= count:
        raise HTTPException(status_code=429, detail={"code": "rate_limited"})
    hits.append(now)


def _guard(call):
    try:
        return call()
    except growth.GrowthError as error:
        raise HTTPException(status_code=error.status, detail={"code": error.code}) from error


def _account(auth: AuthContext) -> str:
    production = settings.deployment_stage.lower() == "production"
    if not auth.user_id or auth.user_id == "anonymous" or (production and not auth.verified):
        raise HTTPException(status_code=401, detail={"code": "sign_in_required"})
    return auth.user_id


@router.get("/status")
async def public_status() -> dict:
    return await asyncio.to_thread(growth.status)


@router.get("/flags")
async def client_flags(request: Request, auth: AuthContext = Depends(get_auth_context)) -> dict:
    key = f"user:{auth.user_id}" if auth.user_id and auth.user_id != "anonymous" else None
    return {"flags": await asyncio.to_thread(admin.flags_for, key)}


class NewsletterRequest(BaseModel):
    email: str = Field(max_length=254)
    consent: bool
    language: str = Field(default="en", max_length=16)
    source: str = Field(default="website", max_length=40)


@router.post("/newsletter")
async def newsletter(payload: NewsletterRequest, request: Request) -> dict:
    _limit(request, "newsletter")
    if not await asyncio.to_thread(admin.flag_enabled, "growth.newsletter"):
        raise HTTPException(status_code=404, detail={"code": "not_found"})
    return await asyncio.to_thread(lambda: _guard(lambda: growth.subscribe(payload.email, consent=payload.consent, language=payload.language, source=payload.source)))


class TokenRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


@router.post("/newsletter/confirm")
async def newsletter_confirm(payload: TokenRequest) -> dict:
    return await asyncio.to_thread(lambda: _guard(lambda: growth.confirm(payload.token)))


@router.post("/newsletter/unsubscribe")
async def newsletter_unsubscribe(payload: TokenRequest) -> dict:
    return await asyncio.to_thread(growth.unsubscribe, payload.token)


class ContactRequest(BaseModel):
    name: str = Field(default="", max_length=120)
    email: str = Field(max_length=254)
    topic: str = Field(default="general", max_length=20)
    message: str = Field(min_length=1, max_length=5000)
    language: str = Field(default="en", max_length=16)
    website: str = Field(default="", max_length=200)  # honeypot: real people leave it empty


@router.post("/contact", status_code=201)
async def contact(payload: ContactRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> dict:
    _limit(request, "contact")
    if payload.website:
        return {"id": "msg_ignored", "status": "received"}  # silently drop bots
    user_id = auth.user_id if auth.user_id and auth.user_id != "anonymous" else None
    return await asyncio.to_thread(lambda: _guard(lambda: growth.contact(name=payload.name, email=payload.email, topic=payload.topic, message=payload.message, language=payload.language, user_id=user_id)))


class PageviewRequest(BaseModel):
    path: str = Field(max_length=500)
    referrer: str = Field(default="", max_length=500)
    language: str = Field(default="", max_length=16)


@router.post("/pageview", status_code=204)
async def pageview(payload: PageviewRequest, request: Request) -> None:
    if request.headers.get("dnt") == "1" or request.headers.get("sec-gpc") == "1":
        return  # Do Not Track / Global Privacy Control respected
    _limit(request, "pageview")
    await asyncio.to_thread(
        growth.record_pageview, path=payload.path, referrer=payload.referrer, language=payload.language,
        client=request.client.host if request.client else "unknown", user_agent=request.headers.get("user-agent", "")[:300],
    )
    return


@router.get("/referral")
async def referral(auth: AuthContext = Depends(get_auth_context)) -> dict:
    user_id = _account(auth)
    if not await asyncio.to_thread(admin.flag_enabled, "growth.referrals", f"user:{user_id}"):
        raise HTTPException(status_code=404, detail={"code": "not_found"})
    return await asyncio.to_thread(growth.referral, user_id)


class RedeemRequest(BaseModel):
    code: str = Field(min_length=4, max_length=20)


@router.post("/referral/redeem")
async def redeem(payload: RedeemRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> dict:
    _limit(request, "redeem")
    user_id = _account(auth)
    return await asyncio.to_thread(lambda: _guard(lambda: growth.redeem(user_id, payload.code)))
