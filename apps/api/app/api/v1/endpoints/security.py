from fastapi import APIRouter

from app.schemas.security import SecurityComplianceRequest, SecurityComplianceResponse
from app.services.security.compliance import SecurityComplianceService

router = APIRouter()
service = SecurityComplianceService()


@router.post("/", response_model=SecurityComplianceResponse)
async def security_posture(payload: SecurityComplianceRequest) -> SecurityComplianceResponse:
    return service.evaluate(payload)

