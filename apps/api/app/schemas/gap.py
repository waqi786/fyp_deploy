from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.paper import PaperRecord

# --------------------------------------------------------------------------- legacy report (used by the gap agent)


class GapReportRequest(BaseModel):
    papers: list[PaperRecord] = Field(min_length=2, max_length=50)
    focus: str = "general"
    current_year: int = 2026


class WhiteSpaceEntry(BaseModel):
    topic: str
    density: float
    whitespace_score: float
    supporting_paper_ids: list[str] = Field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    gap_type: str = "topic"


class ContradictionEvidenceEntry(BaseModel):
    summary: str
    positive_paper_id: str
    negative_paper_id: str
    supporting_evidence: list[str] = Field(default_factory=list)


class FutureWorkSuggestion(BaseModel):
    paper_id: str
    suggestion: str
    evidence: str | None = None


class GapReportResponse(BaseModel):
    unstudied_combinations: list[dict[str, str | float | list[str]]] = Field(default_factory=list)
    white_space_map: list[WhiteSpaceEntry] = Field(default_factory=list)
    white_space_visual_map: list[dict[str, str | float | list[str]]] = Field(default_factory=list)
    contradiction_evidence: list[ContradictionEvidenceEntry] = Field(default_factory=list)
    future_work_suggestions: list[FutureWorkSuggestion] = Field(default_factory=list)
    publication_volume_trend: dict[str, int] = Field(default_factory=dict)
    publication_volume_chart: list[dict[str, int]] = Field(default_factory=list)
    emerging_topics: list[str] = Field(default_factory=list)
    declining_topics: list[str] = Field(default_factory=list)
    method_adoption_curves: dict[str, list[int]] = Field(default_factory=dict)
    method_adoption_chart: list[dict[str, str | int]] = Field(default_factory=list)
    dataset_popularity: dict[str, int] = Field(default_factory=dict)
    dataset_popularity_trend: list[dict[str, str | int]] = Field(default_factory=list)
    geography_distribution: dict[str, int] = Field(default_factory=dict)
    institutional_distribution_map: list[dict[str, str | int | float]] = Field(default_factory=list)
    funding_trend_correlation: list[dict[str, str | int | float]] = Field(default_factory=list)
    coauthorship_evolution: list[dict[str, str | int]] = Field(default_factory=list)
    coauthorship_network_evolution: list[dict[str, str | int | list[str]]] = Field(default_factory=list)
    cross_disciplinary_gaps: list[str] = Field(default_factory=list)
    underexplored_population_flags: list[str] = Field(default_factory=list)
    benchmark_saturation: list[str] = Field(default_factory=list)
    recent_preprint_radar: list[str] = Field(default_factory=list)
    recent_preprint_details: list[dict[str, str | int]] = Field(default_factory=list)
    export_markdown: str = ""
    export_json: str = ""
    export_csv: str = ""
    research_questions: list[str] = Field(default_factory=list)
    trend_summary: dict[str, list[str] | dict[str, int]] = Field(default_factory=dict)
    generated_at: str | None = None


# --------------------------------------------------------------------------- Gaps tab


class GapPaper(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=600)
    abstract: str | None = Field(default=None, max_length=12000)
    year: int | None = Field(default=None, ge=1000, le=2200)
    venue: str | None = Field(default=None, max_length=300)
    authors: list[str] = Field(default_factory=list, max_length=200)
    institutions: list[str] = Field(default_factory=list, max_length=200)
    citation_count: int = Field(default=0, ge=0)
    datasets: list[str] = Field(default_factory=list, max_length=50)
    methods: list[str] = Field(default_factory=list, max_length=50)
    study_type: str | None = Field(default=None, max_length=120)
    sample_size: int | None = Field(default=None, ge=0)
    is_open_access: bool = False


class GapScope(BaseModel):
    kind: Literal["project", "collection", "library", "topic", "comparison"]
    id: str | None = Field(default=None, max_length=200)
    label: str = Field(default="", max_length=300)

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.id or self.label.strip().lower()}"[:400]


class GapAnalyzeRequest(BaseModel):
    papers: list[GapPaper] = Field(min_length=2, max_length=300)
    scope: GapScope
    current_year: int | None = Field(default=None, ge=1900, le=2200)


class GapAnalyzeResponse(BaseModel):
    scope_key: str
    paper_count: int
    signals: list[dict[str, Any]]
    trends: dict[str, Any]
    people: dict[str, Any]
    datasets: list[dict[str, Any]]
    states: dict[str, str] = Field(default_factory=dict)


class GapStateRequest(BaseModel):
    scope_key: str = Field(min_length=1, max_length=400)
    state: Literal["saved", "dismissed", "explored", "idea"] | None = None
    snapshot: dict[str, Any] = Field(default_factory=dict)


class GapIdeaRequest(BaseModel):
    scope_key: str = Field(min_length=1, max_length=400)
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(default="", max_length=4000)
    project_id: str | None = None
    snapshot: dict[str, Any] = Field(default_factory=dict)


class GapConsensusRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    papers: list[GapPaper] = Field(min_length=1, max_length=60)
    language: str = Field(default="en", max_length=16)


class GapConsensusRow(BaseModel):
    paper_id: str
    stance: Literal["supports", "opposes", "mixed", "not_addressed"]
    reason: str = ""
    quote: str = ""


class GapConsensusResponse(BaseModel):
    mode: Literal["ai", "keywords"]
    rows: list[GapConsensusRow]
    counts: dict[str, int]
    credits_used: int = 0


class GapHypothesesRequest(BaseModel):
    papers: list[GapPaper] = Field(min_length=3, max_length=300)
    focus: str = Field(default="", max_length=300)
    signals: list[dict[str, Any]] = Field(default_factory=list, max_length=60)
    language: str = Field(default="en", max_length=16)


class GapHypothesesResponse(BaseModel):
    hypotheses: list[dict[str, Any]]
    credits_used: int = 0


class GapRecommendRequest(BaseModel):
    saved: list[GapPaper] = Field(min_length=1, max_length=300)
    candidates: list[GapPaper] = Field(min_length=1, max_length=300)
    notes: list[str] = Field(default_factory=list, max_length=200)
    current_year: int | None = Field(default=None, ge=1900, le=2200)
    limit: int = Field(default=10, ge=1, le=30)


class GapRecommendation(BaseModel):
    paper_id: str
    reason: dict[str, str]


class GapRecommendResponse(BaseModel):
    recommendations: list[GapRecommendation]
