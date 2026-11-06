from fastapi import APIRouter

from app.schemas.verification import CommittedScopeResponse, CompleteFeatureChecklistResponse, FeatureVerificationResponse, ProposalAlignmentResponse, VerificationReportResponse
from app.services.verification.reports import VerificationReportService


router = APIRouter()
service = VerificationReportService()


@router.get("/", response_model=VerificationReportResponse)
async def verification_reports() -> VerificationReportResponse:
    return service.build()


@router.get("/features", response_model=FeatureVerificationResponse)
async def feature_verification() -> FeatureVerificationResponse:
    return service.build_feature_matrix()


@router.get("/proposal", response_model=ProposalAlignmentResponse)
async def proposal_alignment() -> ProposalAlignmentResponse:
    return service.build_proposal_alignment()


@router.get("/complete-list", response_model=CompleteFeatureChecklistResponse)
async def complete_feature_checklist() -> CompleteFeatureChecklistResponse:
    return service.build_complete_feature_checklist()


@router.get("/committed-scope", response_model=CommittedScopeResponse)
async def committed_scope() -> CommittedScopeResponse:
    return service.build_committed_scope()
