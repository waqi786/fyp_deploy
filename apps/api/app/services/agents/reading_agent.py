from app.schemas.agents import MultiAgentWorkflowRequest, ReadingAgentOutput, SearchAgentOutput
from app.schemas.document import DocumentExtractionResponse
from app.services.agents.templates import AGENT_PROMPT_TEMPLATES
from app.services.documents.pdf_extraction import DocumentExtractionService
from app.services.summarization.extractive import ExtractiveSummarizer


class ReadingExtractionAgent:
    def __init__(self) -> None:
        self.extractor = DocumentExtractionService()
        self.summarizer = ExtractiveSummarizer()

    def run(self, payload: MultiAgentWorkflowRequest, search_output: SearchAgentOutput) -> ReadingAgentOutput:
        source_text = payload.raw_text or "\n".join(filter(None, [paper.abstract or paper.title for paper in search_output.top_papers[:6]]))
        extraction = self._extract(source_text)
        summary = self.summarizer.summarize(
            payload.focus or payload.question,
            extraction.extracted_text or source_text or payload.question,
            language=payload.language,
            audience="expert",
            summary_length="long",
        )
        return ReadingAgentOutput(
            prompt_template=AGENT_PROMPT_TEMPLATES["reading"],
            retrieval_scope="top ranked evidence plus multimodal extraction context",
            summary=summary,
            extraction=extraction,
        )

    def _extract(self, text: str) -> DocumentExtractionResponse:
        return self.extractor.extract_sync_text(text)
