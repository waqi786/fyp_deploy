from fastapi import APIRouter

from app.schemas.mobile import MobileExperienceRequest, MobileExperienceResponse
from app.services.mobile.experience import MobileExperienceService


router = APIRouter()
service = MobileExperienceService()


@router.post("/", response_model=MobileExperienceResponse)
async def mobile_experience(payload: MobileExperienceRequest) -> MobileExperienceResponse:
    return service.build(payload)

