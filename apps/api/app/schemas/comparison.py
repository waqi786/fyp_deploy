from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.paper import PaperRecord


class ComparisonRequest(BaseModel):
    papers: list[PaperRecord] = Field(min_length=2, max_length=15)
    focus: str = "general"
    custom_columns: list[str] = Field(default_factory=list, max_length=25)
    pinned_paper_ids: list[str] = Field(default_factory=list)
    criterion: str | None = None

    @model_validator(mode="after")
    def deduplicate_papers(self) -> "ComparisonRequest":
        unique_papers: dict[str, PaperRecord] = {}
        for paper in self.papers:
            unique_papers.setdefault(paper.paper_id, paper)
        self.papers = list(unique_papers.values())
        if not 2 <= len(self.papers) <= 15:
            raise ValueError("Select between 2 and 15 unique papers.")
        return self

    @field_validator("custom_columns")
    @classmethod
    def validate_custom_columns(cls, columns: list[str]) -> list[str]:
        cleaned, seen = [], set()
        for column in columns:
            value = " ".join(column.split())
            if not value or len(value) > 120:
                raise ValueError("Column names must contain 1 to 120 characters.")
            key = value.casefold()
            if key not in seen:
                cleaned.append(value)
                seen.add(key)
        return cleaned


class ComparisonRow(BaseModel):
    paper_id: str
    title: str
    source_url: str | None = None
    full_text_source_url: str | None = None
    discovery_source: str | None = None
    year: int | None = None
    venue: str | None = None
    citation: str = ""
    citation_count: int = 0
    open_access: bool = False
    abstract_available: bool = False
    full_text_available: bool = False
    full_text_status: str = "not_attempted"
    full_text_source: str | None = None
    document_type: str = "research_article"
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    extracted_columns: dict[str, str] = Field(default_factory=dict)
    evidence: dict[str, str] = Field(default_factory=dict)
    evidence_source: dict[str, str] = Field(default_factory=dict)
    confidence_by_column: dict[str, str] = Field(default_factory=dict)
    similarity_score: float = 0.0
    method_similarity_score: float = 0.0
    dataset_similarity_score: float = 0.0
    result_similarity_score: float = 0.0
    methods: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    result_metrics: dict[str, float] = Field(default_factory=dict)
    significance_note: str = ""
    pinned: bool = False


class PaperProfile(BaseModel):
    paper_id: str
    profile_version: int = 2
    doi: str | None = None
    publication_year: int | None = None
    preprint_notice: str | None = None
    research_questions: list[dict[str, Any]] = Field(default_factory=list)
    motivation: list[dict[str, Any]] = Field(default_factory=list)
    contributions: list[dict[str, Any]] = Field(default_factory=list)
    baselines: list[dict[str, Any]] = Field(default_factory=list)
    experiments: list[dict[str, Any]] = Field(default_factory=list)
    strongest_experiment: dict[str, Any] | None = None
    ablation: list[dict[str, Any]] = Field(default_factory=list)
    datasets_detail: list[dict[str, Any]] = Field(default_factory=list)
    reproducibility: dict[str, Any] = Field(default_factory=dict)
    repo_url: str | None = None
    frameworks: list[dict[str, Any]] = Field(default_factory=list)
    future_work: list[dict[str, Any]] = Field(default_factory=list)
    authors_affiliations: list[dict[str, Any]] = Field(default_factory=list)
    parsed_references: list[dict[str, Any]] = Field(default_factory=list)
    key_tables: list[dict[str, Any]] = Field(default_factory=list)
    key_figures: list[dict[str, Any]] = Field(default_factory=list)
    evidence_pages: list[dict[str, Any]] = Field(default_factory=list)


class InsightEvidenceRef(BaseModel):
    paper_id: str
    field: str
    quote: str = Field(min_length=1, max_length=1200)
    page: int | None = Field(default=None, ge=1)


class InsightKeyNumber(BaseModel):
    value: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=160)
    evidence: list[InsightEvidenceRef] = Field(min_length=1, max_length=15)


class InsightHeadToHeadPoint(BaseModel):
    paper_id: str
    value: float
    evidence: InsightEvidenceRef


class InsightHeadToHead(BaseModel):
    dataset: str
    metric: str
    split: str
    points: list[InsightHeadToHeadPoint] = Field(min_length=2, max_length=15)


class InsightsModel(BaseModel):
    """Deterministic, evidence-linked facts for the Compare Insights UI."""

    version: int = 1
    takeaway: str = Field(min_length=1, max_length=360)
    takeaway_evidence: list[InsightEvidenceRef] = Field(default_factory=list, max_length=15)
    key_numbers: list[InsightKeyNumber] = Field(default_factory=list, max_length=3)
    head_to_head: InsightHeadToHead | None = None
    generated_from_full_text: bool = True

    @field_validator("takeaway")
    @classmethod
    def limit_takeaway_words(cls, value: str) -> str:
        if len(value.split()) > 25:
            raise ValueError("The takeaway must be 25 words or fewer.")
        return value


class ComparisonResponse(BaseModel):
    focus: str
    rows: list[ComparisonRow]
    comparison_count: int
    max_supported_papers: int
    auto_suggested_columns: list[str] = Field(default_factory=list)
    custom_columns_resolved: list[str]
    contradiction_highlights: list[str]
    leaderboard: list[str]
    grouped_methods: dict[str, list[str]]
    similarity_heatmap: list[list[float]]
    method_similarity_heatmap: list[list[float]] = Field(default_factory=list)
    dataset_similarity_heatmap: list[list[float]] = Field(default_factory=list)
    result_similarity_heatmap: list[list[float]] = Field(default_factory=list)
    heatmap_labels: list[str]
    methodology_dendrogram: dict[str, list[str]]
    dendrogram_edges: list[dict[str, str | float]] = Field(default_factory=list)
    timeline: list[dict[str, str | int]]
    performance_leaderboard_by_dataset: dict[str, list[str]] = Field(default_factory=dict)
    best_paper_recommendation: str
    dataset_overlap: dict[str, list[str]]
    dataset_overlap_matrix: list[list[int]] = Field(default_factory=list)
    citation_overlap_venn: dict[str, int]
    citation_overlap_sets: dict[str, list[str]] = Field(default_factory=dict)
    narrative_summary: str
    export_markdown: str
    export_csv: str
    export_latex: str
    export_json: str
    comparison_snapshot_id: str
    shareable_link_token: str
    shareable_url: str
    snapshot_metadata: dict[str, str | int | list[str]]
    literature_review_section: str
    literature_review_export_job: dict[str, str] = Field(default_factory=dict)
    pinned_row_order: list[str] = Field(default_factory=list)
    paper_profiles: list[PaperProfile] = Field(default_factory=list)
    insight_run_id: str | None = None
    insights_cached: bool = False
    insights_model: InsightsModel | None = None

    @model_validator(mode="after")
    def validate_insight_sources(self) -> "ComparisonResponse":
        model = self.insights_model
        if model is None:
            return self
        row_ids = {row.paper_id for row in self.rows}
        def collect_quotes(value: Any) -> list[str]:
            if isinstance(value, dict):
                quotes = [str(value["quote"]).casefold()] if value.get("quote") else []
                return quotes + [quote for child in value.values() for quote in collect_quotes(child)]
            if isinstance(value, list):
                return [quote for child in value for quote in collect_quotes(child)]
            return []

        profile_sources = {
            profile.paper_id: collect_quotes(profile.model_dump(mode="python"))
            for profile in self.paper_profiles
        }
        row_sources = {
            row.paper_id: [str(quote).casefold() for quote in row.evidence.values() if quote]
            for row in self.rows
        }

        def validate_reference(reference: InsightEvidenceRef) -> None:
            if reference.paper_id not in row_ids:
                raise ValueError("Insight evidence must refer to a selected paper.")
            quote = " ".join(reference.quote.casefold().split())
            sources = profile_sources.get(reference.paper_id, []) + row_sources.get(reference.paper_id, [])
            if not any(quote in " ".join(source.split()) for source in sources):
                raise ValueError("Insight evidence quotes must match extracted paper text.")

        for reference in model.takeaway_evidence:
            validate_reference(reference)
        for number in model.key_numbers:
            for reference in number.evidence:
                validate_reference(reference)
        if model.head_to_head:
            for point in model.head_to_head.points:
                validate_reference(point.evidence)
                if point.paper_id != point.evidence.paper_id:
                    raise ValueError("Head-to-head values must link to their own paper's evidence.")
        return self
