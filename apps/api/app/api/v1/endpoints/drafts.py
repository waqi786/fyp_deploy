from fastapi import APIRouter

from app.schemas.draft import DraftGenerationRequest, DraftGenerationResponse
from app.services.writing.draft_generation import DraftGenerationService

router = APIRouter()
service = DraftGenerationService()


@router.post("/generate", response_model=DraftGenerationResponse)
async def generate_draft(payload: DraftGenerationRequest) -> DraftGenerationResponse:
    return service.generate(
        title=payload.title,
        extracted_text=payload.extracted_text,
        figures=payload.figures,
        target_style=payload.target_style,
        language=payload.language,
    )
