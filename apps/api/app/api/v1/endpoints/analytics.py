from fastapi import APIRouter

from app.schemas.analytics import AnalyticsRequest, AnalyticsResponse
from app.services.analytics.dashboard import AnalyticsService

router = APIRouter()
service = AnalyticsService()


@router.post("/", response_model=AnalyticsResponse)
async def analytics(payload: AnalyticsRequest) -> AnalyticsResponse:
    return service.build(payload)
