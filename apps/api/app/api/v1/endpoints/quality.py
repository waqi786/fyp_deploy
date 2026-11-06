from fastapi import APIRouter

from app.schemas.quality import (
    LaunchReadinessResponse,
    NonFunctionalQualityRequest,
    NonFunctionalQualityResponse,
    TraceabilityCheckRequest,
    TraceabilityCheckResponse,
)
from app.services.quality.launch_readiness import LaunchReadinessService
from app.services.quality.requirements import NonFunctionalQualityService
from app.services.quality.traceability import TraceabilityGuardService


router = APIRouter()
quality_service = NonFunctionalQualityService()
traceability_service = TraceabilityGuardService()
launch_readiness_service = LaunchReadinessService()


@router.post("/traceability", response_model=TraceabilityCheckResponse)
async def traceability(payload: TraceabilityCheckRequest) -> TraceabilityCheckResponse:
    return traceability_service.validate(payload)


@router.post("/assessment", response_model=NonFunctionalQualityResponse)
async def non_functional_assessment(payload: NonFunctionalQualityRequest) -> NonFunctionalQualityResponse:
    return quality_service.assess(payload)


@router.get("/launch-readiness", response_model=LaunchReadinessResponse)
async def launch_readiness() -> LaunchReadinessResponse:
    return launch_readiness_service.audit()
