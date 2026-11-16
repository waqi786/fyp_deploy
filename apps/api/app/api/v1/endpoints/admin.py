"""Admin console API (/api/v1/admin). Server-enforced admin role; every change is audited.

Admins are listed in ADMIN_USER_IDS (comma-separated account ids). In production the sign-in must be verified
(signed JWT); the unsigned development header is accepted only outside production.
"""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import AuthContext, get_auth_context
from app.core.config import settings
from app.services.admin import service as admin
from app.services.growth import service as growth

router = APIRouter()


def admin_ids() -> set[str]:
    raw = os.getenv("ADMIN_USER_IDS", "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def require_admin(auth: AuthContext = Depends(get_auth_context)) -> str:
    production = settings.deployment_stage.lower() == "production"
    if not auth.user_id or auth.user_id == "anonymous" or (production and not auth.verified):
        raise HTTPException(status_code=401, detail={"code": "sign_in_required"})
    if auth.user_id not in admin_ids():
        raise HTTPException(status_code=403, detail={"code": "forbidden"})
    return auth.user_id


def _guard(call):
    try:
        return call()
    except admin.AdminError as error:
        raise HTTPException(status_code=error.status, detail={"code": error.code}) from error
    except growth.GrowthError as error:
        raise HTTPException(status_code=error.status, detail={"code": error.code}) from error


@router.get("/me")
async def me(actor: str = Depends(require_admin)) -> dict:
    return {"user_id": actor, "admin": True}


@router.get("/overview")
async def overview(_: str = Depends(require_admin)) -> dict:
    return await asyncio.to_thread(admin.overview)


@router.get("/users")
async def users(q: str = "", limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), _: str = Depends(require_admin)) -> dict:
    return await asyncio.to_thread(admin.users, q[:120], limit, offset)


@router.get("/users/{user_id}")
async def user(user_id: str, _: str = Depends(require_admin)) -> dict:
    return await asyncio.to_thread(admin.user_detail, user_id)


class GrantRequest(BaseModel):
    credits: int = Field(ge=1, le=100000)
    reason: str = Field(min_length=3, max_length=300)


@router.post("/users/{user_id}/credits")
async def grant(user_id: str, payload: GrantRequest, actor: str = Depends(require_admin)) -> dict:
    return await asyncio.to_thread(lambda: _guard(lambda: admin.grant_credits(actor, user_id, payload.credits, payload.reason)))


class SuspendRequest(BaseModel):
    suspended: bool
    reason: str | None = Field(default=None, max_length=300)


@router.post("/users/{user_id}/suspension")
async def suspend(user_id: str, payload: SuspendRequest, actor: str = Depends(require_admin)) -> dict:
    return await asyncio.to_thread(lambda: _guard(lambda: admin.set_suspended(actor, user_id, payload.suspended, payload.reason)))


@router.get("/providers")
async def providers(_: str = Depends(require_admin)) -> dict:
    from app.services.ai_router import get_default_router
    from app.services.listen.tts import get_tts_router

    def collect() -> dict:
        ai = get_default_router()
        try:
            from app.services.ai_router.router import load_routes

            routes = {task: [f"{route.provider}:{getattr(route, 'model', '')}" for route in items] for task, items in load_routes().items()}
        except Exception:  # noqa: BLE001
            routes = {}
        return {"ai": ai.provider_health(), "routes": routes, "tts": get_tts_router().health(), "voices": get_tts_router().registry()}

    return await asyncio.to_thread(collect)


@router.post("/providers/{name}/probe")
async def probe(name: str, actor: str = Depends(require_admin)) -> dict:
    from app.services.ai_router import get_default_router

    ai = get_default_router()
    if name not in ai.providers:
        raise HTTPException(status_code=404, detail={"code": "not_found"})
    result = await asyncio.to_thread(ai.probe_provider, name)
    await asyncio.to_thread(admin.audit, actor, "provider.probe", name, {"healthy": result.get("healthy")})
    return result


@router.get("/flags")
async def list_flags(_: str = Depends(require_admin)) -> dict:
    return {"flags": await asyncio.to_thread(admin.flags)}


class FlagRequest(BaseModel):
    enabled: bool
    rollout: int = Field(default=100, ge=0, le=100)
    description: str | None = Field(default=None, max_length=300)
    allow_users: list[str] | None = Field(default=None, max_length=500)


@router.put("/flags/{key}")
async def put_flag(key: str, payload: FlagRequest, actor: str = Depends(require_admin)) -> dict:
    return await asyncio.to_thread(lambda: _guard(lambda: admin.set_flag(actor, key, enabled=payload.enabled, rollout=payload.rollout, description=payload.description, allow_users=payload.allow_users)))


@router.delete("/flags/{key}", status_code=204)
async def delete_flag(key: str, actor: str = Depends(require_admin)) -> None:
    await asyncio.to_thread(admin.delete_flag, actor, key)


@router.get("/jobs")
async def jobs(_: str = Depends(require_admin)) -> dict:
    def collect() -> dict:
        try:
            from app.services.catalog.service import get_catalog_service

            runs = get_catalog_service().runs(20)
        except Exception:  # noqa: BLE001 - the catalog is optional
            runs = []
        return {"pipeline_runs": runs, "dead_letters": admin.dead_letters()}

    return await asyncio.to_thread(collect)


@router.post("/jobs/dead-letters/{entry_id}/retry")
async def retry(entry_id: str, actor: str = Depends(require_admin)) -> dict:
    return await asyncio.to_thread(lambda: _guard(lambda: admin.retry_dead_letter(actor, entry_id)))


@router.post("/jobs/dead-letters/{entry_id}/discard", status_code=204)
async def discard(entry_id: str, actor: str = Depends(require_admin)) -> None:
    await asyncio.to_thread(admin.discard_dead_letter, actor, entry_id)


@router.get("/audit")
async def audit(action: str | None = None, limit: int = Query(default=100, ge=1, le=500), _: str = Depends(require_admin)) -> dict:
    return {"entries": await asyncio.to_thread(admin.audit_log, limit, action)}


@router.get("/messages")
async def messages(status: str | None = None, _: str = Depends(require_admin)) -> dict:
    return {"messages": await asyncio.to_thread(growth.contact_messages, status)}


class MessageStatus(BaseModel):
    status: str = Field(pattern="^(open|closed)$")


@router.post("/messages/{message_id}/status")
async def message_status(message_id: str, payload: MessageStatus, actor: str = Depends(require_admin)) -> dict:
    await asyncio.to_thread(lambda: _guard(lambda: growth.set_contact_status(message_id, payload.status)))
    await asyncio.to_thread(admin.audit, actor, "message.status", message_id, {"status": payload.status})
    return {"id": message_id, "status": payload.status}


class IncidentRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    component: str
    severity: str
    status: str
    message: str = Field(default="", max_length=2000)


@router.get("/incidents")
async def list_incidents(_: str = Depends(require_admin)) -> dict:
    return {"incidents": await asyncio.to_thread(admin.incidents, True, 100)}


@router.post("/incidents", status_code=201)
async def create_incident(payload: IncidentRequest, actor: str = Depends(require_admin)) -> dict:
    return await asyncio.to_thread(lambda: _guard(lambda: admin.save_incident(actor, incident_id=None, **payload.model_dump())))


@router.put("/incidents/{incident_id}")
async def update_incident(incident_id: str, payload: IncidentRequest, actor: str = Depends(require_admin)) -> dict:
    return await asyncio.to_thread(lambda: _guard(lambda: admin.save_incident(actor, incident_id=incident_id, **payload.model_dump())))
