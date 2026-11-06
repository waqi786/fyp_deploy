from fastapi import APIRouter

from app.schemas.summary import (
    ParagraphExplainRequest,
    ParagraphExplainResponse,
    SummaryRequest,
    SummaryResponse,
)
from app.services.summarization.extractive import ExtractiveSummarizer

router = APIRouter()
summarizer = ExtractiveSummarizer()


@router.post("/", response_model=SummaryResponse)
async def summarize(payload: SummaryRequest) -> SummaryResponse:
    return summarizer.summarize(
        payload.title,
        payload.content,
        payload.language,
        payload.audience,
        payload.summary_length,
        payload.target_languages,
    )


@router.post("/explain", response_model=ParagraphExplainResponse)
async def explain_paragraph(payload: ParagraphExplainRequest) -> ParagraphExplainResponse:
    return ParagraphExplainResponse(**summarizer.explain(payload.paragraph, payload.audience, payload.language))
