import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.api.deps import AuthContext, get_auth_context
from app.api.v1.router import api_router
from app.core.config import settings
from app.services.ai_router import get_default_router
from app.services.search.translation import (
    start_translation_retry_worker,
    translation_budget_status,
    translation_metrics,
    translation_provider_health,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    testing = os.getenv("RESORA_TESTING") == "1"
    if not testing:
        await asyncio.to_thread(start_translation_retry_worker)
    tasks: list[asyncio.Task] = []
    if not testing:
        async def ai_router_monitor() -> None:
            interval = max(60, int(settings.ai_router_health_probe_seconds))
            while True:
                await asyncio.sleep(interval)
                try:
                    router = get_default_router()
                    for provider_name in router.providers:
                        await asyncio.to_thread(router.probe_provider, provider_name)
                except Exception:
                    pass

        tasks = [asyncio.create_task(ai_router_monitor())]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


def _cors_origins(raw: str) -> list[str]:
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    return origins or ["http://127.0.0.1:5173"]


app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(settings.cors_allowed_origins),
    allow_origin_regex=(
        r"^https?://(?:localhost|127\.0\.0\.1)(?::\d+)?$"
        if settings.deployment_stage == "development"
        else None
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
@app.get("/admin/translation/health", tags=["admin"])
async def translation_health(auth: AuthContext = Depends(get_auth_context)) -> dict[str, object]:
    allowed = {item.strip() for item in settings.translation_admin_user_ids.split(",") if item.strip()}
    if not auth.verified or auth.user_id not in allowed:
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"providers": translation_provider_health(), "usage": translation_metrics(), "budgets": translation_budget_status()}


@app.get("/admin/ai-router/health", tags=["admin"])
async def ai_router_health(auth: AuthContext = Depends(get_auth_context)) -> dict[str, object]:
    allowed = {item.strip() for item in settings.translation_admin_user_ids.split(",") if item.strip()}
    if not auth.verified or auth.user_id not in allowed:
        raise HTTPException(status_code=403, detail="Admin access required")
    router = get_default_router()
    return {"providers": router.provider_health(), "metrics": router.metrics()}


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    return {"service": settings.app_name, "status": "ok"}


@app.get("/health", tags=["root"])
async def health() -> dict[str, str]:
    return {"service": settings.app_name, "status": "healthy"}


@app.get("/ready", tags=["root"])
async def ready() -> dict[str, str]:
    return {"service": settings.app_name, "status": "ready"}


@app.get("/metrics", tags=["root"], response_class=PlainTextResponse)
async def metrics() -> str:
    return "# HELP resora_service_up Service availability\n# TYPE resora_service_up gauge\nresora_service_up 1\n"
