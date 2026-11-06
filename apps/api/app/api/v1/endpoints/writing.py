from fastapi import APIRouter

from app.schemas.writing import LiteratureReviewRequest, LiteratureReviewResponse
from app.services.writing.literature_review import LiteratureReviewService


router = APIRouter()
service = LiteratureReviewService()


@router.post("/literature-review", response_model=LiteratureReviewResponse)
async def generate_literature_review(payload: LiteratureReviewRequest) -> LiteratureReviewResponse:
    return service.generate(payload)
