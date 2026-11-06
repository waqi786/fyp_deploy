from app.schemas.agents import (
    MultiAgentWorkflowRequest,
    ReadingAgentOutput,
    WritingAgentOutput,
)
from app.schemas.writing import LiteratureReviewRequest
from app.services.agents.templates import AGENT_PROMPT_TEMPLATES
from app.services.writing.draft_generation import DraftGenerationService
from app.services.writing.literature_review import LiteratureReviewService


class WritingAgent:
    def __init__(self) -> None:
        self.drafts = DraftGenerationService()
        self.reviews = LiteratureReviewService()

    def run(self, payload: MultiAgentWorkflowRequest, reading_output: ReadingAgentOutput) -> WritingAgentOutput:
        extraction = reading_output.extraction
        draft = self.drafts.generate(
            title=payload.focus or payload.question,
            extracted_text=extraction.extracted_text,
            figures=extraction.figures,
            target_style=payload.target_style,
            language=payload.language,
        )
        review = self.reviews.generate(
            LiteratureReviewRequest(
                title=payload.focus or payload.question,
                extracted_text=extraction.extracted_text,
                figures=extraction.figures,
                tables=extraction.tables,
                target_style=payload.target_style,
                language=payload.language,
                comments=["Generated from multi-agent writing workflow."],
            )
        )
        return WritingAgentOutput(
            prompt_template=AGENT_PROMPT_TEMPLATES["writing"],
            retrieval_scope="writing-ready evidence, extracted visuals, and self-critique",
            draft=draft,
            literature_review=review,
        )

