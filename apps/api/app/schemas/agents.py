from pydantic import BaseModel, Field

from app.schemas.comparison import ComparisonResponse
from app.schemas.document import DocumentExtractionResponse
from app.schemas.draft import DraftGenerationResponse
from app.schemas.export import CitationExportResponse
from app.schemas.gap import GapReportResponse
from app.schemas.graph import CitationGraphResponse
from app.schemas.paper import PaperRecord
from app.schemas.summary import SummaryResponse
from app.schemas.trust import TrustAnalysisResponse
from app.schemas.writing import LiteratureReviewResponse


class PlannerDecision(BaseModel):
    primary_route: str
    specialist_sequence: list[str] = Field(default_factory=list)
    retrieval_scope: str
    prompt_template: str
    rationale: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0


class AgentStateTransition(BaseModel):
    state: str
    status: str
    note: str


class MultiAgentWorkflowRequest(BaseModel):
    question: str
    papers: list[PaperRecord] = Field(default_factory=list)
    raw_text: str = ""
    language: str = "en"
    focus: str = "general"
    current_year: int = 2026
    citation_contexts: list[str] = Field(default_factory=list)
    custom_columns: list[str] = Field(default_factory=list)
    target_style: str = "ieee"


class SearchAgentOutput(BaseModel):
    prompt_template: str
    retrieval_scope: str
    providers: list[str] = Field(default_factory=list)
    total_candidates: int = 0
    deduplicated_results: int = 0
    likely_duplicate_pairs: list[list[str]] = Field(default_factory=list)
    top_papers: list[PaperRecord] = Field(default_factory=list)
    rationale: str = ""


class ReadingAgentOutput(BaseModel):
    prompt_template: str
    retrieval_scope: str
    summary: SummaryResponse
    extraction: DocumentExtractionResponse


class ComparisonAgentOutput(BaseModel):
    prompt_template: str
    retrieval_scope: str
    comparison: ComparisonResponse


class CritiqueAgentOutput(BaseModel):
    prompt_template: str
    retrieval_scope: str
    trust_reports: list[TrustAnalysisResponse] = Field(default_factory=list)
    contradiction_rollup: list[str] = Field(default_factory=list)


class GapAgentOutput(BaseModel):
    prompt_template: str
    retrieval_scope: str
    report: GapReportResponse


class WritingAgentOutput(BaseModel):
    prompt_template: str
    retrieval_scope: str
    draft: DraftGenerationResponse
    literature_review: LiteratureReviewResponse


class CitationAgentOutput(BaseModel):
    prompt_template: str
    retrieval_scope: str
    bibtex: CitationExportResponse
    ris: CitationExportResponse
    csljson: CitationExportResponse
    citation_context_answers: list[str] = Field(default_factory=list)
    graph_metrics: CitationGraphResponse


class MultiAgentWorkflowResponse(BaseModel):
    planner: PlannerDecision
    state_history: list[AgentStateTransition] = Field(default_factory=list)
    search: SearchAgentOutput | None = None
    reading: ReadingAgentOutput | None = None
    comparison: ComparisonAgentOutput | None = None
    critique: CritiqueAgentOutput | None = None
    gap: GapAgentOutput | None = None
    writing: WritingAgentOutput | None = None
    citation: CitationAgentOutput | None = None
    final_answer: str
    citations: list[str] = Field(default_factory=list)

