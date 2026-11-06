from fastapi import APIRouter

from app.schemas.roadmap import RoadmapResponse
from app.services.roadmap.planner import DevelopmentRoadmapService

router = APIRouter()
service = DevelopmentRoadmapService()


@router.get("/", response_model=RoadmapResponse)
async def roadmap() -> RoadmapResponse:
    return service.build()

