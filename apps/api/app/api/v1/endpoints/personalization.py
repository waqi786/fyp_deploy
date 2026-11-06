from fastapi import APIRouter

from app.schemas.personalization import PersonalizationRequest, PersonalizationResponse
from app.services.personalization.profile import PersonalizationService

router = APIRouter()
service = PersonalizationService()


@router.post("/", response_model=PersonalizationResponse)
async def personalize(payload: PersonalizationRequest) -> PersonalizationResponse:
    return service.build(payload)
