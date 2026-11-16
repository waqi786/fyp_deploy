"""Research catalog built by the Big Data pipeline: overview, analytics (trends, hot topics, citation patterns,
coverage, gap candidates), hybrid semantic + keyword search, paper details and pipeline runs."""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import AuthContext, get_auth_context
from app.core.config import settings
from app.services.catalog.service import CatalogUnavailable, get_catalog_service

router = APIRouter()
SOURCES = ("openalex", "arxiv", "crossref", "semantic_scholar")


class CatalogRunRequest(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=10)
    sources: list[str] = Field(default_factory=lambda: list(SOURCES), max_length=4)
    max_records: int = Field(default=200, ge=10, le=5000)
    engine: str = Field(default="local", pattern="^(local|spark)$")


def _service():
    try:
        service = get_catalog_service()
        service.db()
        return service
    except CatalogUnavailable as error:
        raise HTTPException(status_code=503, detail={"code": "catalog_unavailable"}) from error


def _admin(auth: AuthContext) -> str:
    if not auth.user_id or auth.user_id == "anonymous":
        raise HTTPException(status_code=401, detail={"code": "sign_in_required"})
    admins = {item.strip() for item in os.getenv("CATALOG_ADMIN_USER_IDS", "").split(",") if item.strip()}
    if settings.deployment_stage.lower() == "production" and (not auth.verified or auth.user_id not in admins):
        raise HTTPException(status_code=403, detail={"code": "forbidden"})
    return auth.user_id


@router.get("/overview")
async def overview() -> dict:
    return await asyncio.to_thread(_service().overview)


@router.get("/analytics")
async def analytics() -> dict:
    data = await asyncio.to_thread(_service().analytics)
    return data or {"paper_count": 0}


@router.get("/search")
async def search(q: str = Query(min_length=2, max_length=300), limit: int = Query(20, ge=1, le=100), year_from: int | None = None, year_to: int | None = None, open_access: bool | None = None) -> dict:
    return await asyncio.to_thread(_service().search, q, limit=limit, year_from=year_from, year_to=year_to, open_access=open_access)


@router.get("/papers/{paper_id}")
async def paper(paper_id: str) -> dict:
    found = await asyncio.to_thread(_service().paper, paper_id)
    if not found:
        raise HTTPException(status_code=404, detail={"code": "not_found"})
    return found


@router.get("/runs")
async def runs(limit: int = Query(20, ge=1, le=100)) -> dict:
    return {"runs": await asyncio.to_thread(_service().runs, limit)}


@router.post("/runs", status_code=202)
async def start_run(payload: CatalogRunRequest, auth: AuthContext = Depends(get_auth_context)) -> dict:
    _admin(auth)
    if any(source not in SOURCES for source in payload.sources):
        raise HTTPException(status_code=422, detail={"code": "invalid_source"})
    queries = [query.strip()[:200] for query in payload.queries if query.strip()]
    if not queries:
        raise HTTPException(status_code=422, detail={"code": "query_required"})
    try:
        run_id = _service().start_run(queries=queries, sources=payload.sources, max_records=payload.max_records, engine=payload.engine)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail={"code": "busy"}) from error
    return {"run_id": run_id, "status": "running"}
