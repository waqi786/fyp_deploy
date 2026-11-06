from fastapi import APIRouter

from app.schemas.trust import TrustAnalysisRequest, TrustAnalysisResponse
from app.services.critique.trust import TrustAnalysisService

router = APIRouter()
service = TrustAnalysisService()


@router.post("/", response_model=TrustAnalysisResponse)
async def analyze_trust(payload: TrustAnalysisRequest) -> TrustAnalysisResponse:
    return service.analyze(payload)
