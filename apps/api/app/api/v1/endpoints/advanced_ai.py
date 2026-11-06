from fastapi import APIRouter

from app.schemas.advanced import AdvancedAIRequest, AdvancedAIResponse
from app.services.advanced.intelligence import AdvancedIntelligenceService

router = APIRouter()
service = AdvancedIntelligenceService()


@router.post("/", response_model=AdvancedAIResponse)
async def advanced_intelligence(payload: AdvancedAIRequest) -> AdvancedAIResponse:
    return service.analyze(payload)

