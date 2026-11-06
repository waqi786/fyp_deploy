from typing import Literal

from pydantic import BaseModel, Field, field_validator
from app.services.language.config import canonical_language_code

from app.schemas.paper import PaperRecord
from app.services.search.source_ids import DEFAULT_SCHOLARLY_SOURCES


class SearchFilters(BaseModel):
    language: str = "en"
    min_citations: int = Field(default=0, ge=0)
    open_access_only: bool = False
    study_type: str | None = None
    quartile: str | None = None
    sample_size_min: int | None = Field(default=None, ge=0)
    year_from: int | None = Field(default=None, ge=1900)
    year_to: int | None = Field(default=None, le=2100)
    methodology: str | None = None
    author: str | None = None
    venue: str | None = None
    institution: str | None = None
    dataset: str | None = None
    peer_reviewed_only: bool = False
    preprint_only: bool = False
    include_retracted: bool = False
    citation_context: str | None = None
    region: str | None = None
    chemical_formula: str | None = None
    gene_or_protein: str | None = None
    equipment_or_software: str | None = None
    negative_results_only: bool = False
    temporal_aware: bool = False
    patent_overlap: bool = False
    grey_literature: bool = False
    conference_priority: bool = False
    cited_by_quality_only: bool = False
    private_search_vault: bool = True
    collaborative_session: bool = False


class SourceSearchRequest(BaseModel):
    query: str = Field(min_length=2)
    limit: int = Field(default=25, ge=1, le=100)
    page: int = Field(default=1, ge=1)
    filters: SearchFilters = Field(default_factory=SearchFilters)


class SearchRequest(BaseModel):
    query: str = Field(min_length=2)
    limit: int = Field(default=25, ge=1, le=100)
    page: int = Field(default=1, ge=1)
    sources: list[str] = Field(default_factory=lambda: list(DEFAULT_SCHOLARLY_SOURCES))
    language: str = "en"
    query_language: str | None = None
    paper_language: str | None = None
    target_language: str = "en"
    translate_results: bool = False
    min_citations: int = Field(default=0, ge=0)
    open_access_only: bool = False
    study_type: str | None = None
    quartile: str | None = None
    sample_size_min: int | None = Field(default=None, ge=0)
    year_from: int | None = Field(default=None, ge=1900)
    year_to: int | None = Field(default=None, le=2100)
    methodology: str | None = None
    author: str | None = None
    venue: str | None = None
    institution: str | None = None
    dataset: str | None = None
    peer_reviewed_only: bool = False
    preprint_only: bool = False
    include_retracted: bool = False
    citation_context: str | None = None
    region: str | None = None
    chemical_formula: str | None = None
    gene_or_protein: str | None = None
    equipment_or_software: str | None = None
    negative_results_only: bool = False
    temporal_aware: bool = False
    patent_overlap: bool = False
    grey_literature: bool = False
    conference_priority: bool = False
    cited_by_quality_only: bool = False
    private_search_vault: bool = True
    collaborative_session: bool = False
    search_mode: Literal["keyword", "semantic", "hybrid"] = "hybrid"
    query_type: Literal["natural_language", "boolean", "voice", "image"] = "natural_language"
    voice_transcript: str | None = None
    image_caption: str | None = None
    sort_by: Literal["relevance", "citations", "recent"] = "relevance"
    session_id: str | None = None
    save_history: bool = True

    @field_validator("query_language", "paper_language", "target_language")
    @classmethod
    def validate_language_code(cls, value: str | None, info):
        if value is None:
            return value
        if value == "auto" and info.field_name == "query_language":
            return value
        return canonical_language_code(value)

    def to_filters(self) -> SearchFilters:
        return SearchFilters(
            language=self.paper_language or self.language,
            min_citations=self.min_citations,
            open_access_only=self.open_access_only,
            study_type=self.study_type,
            quartile=self.quartile,
            sample_size_min=self.sample_size_min,
            year_from=self.year_from,
            year_to=self.year_to,
            methodology=self.methodology,
            author=self.author,
            venue=self.venue,
            institution=self.institution,
            dataset=self.dataset,
            peer_reviewed_only=self.peer_reviewed_only,
            preprint_only=self.preprint_only,
            include_retracted=self.include_retracted,
            citation_context=self.citation_context,
            region=self.region,
            chemical_formula=self.chemical_formula,
            gene_or_protein=self.gene_or_protein,
            equipment_or_software=self.equipment_or_software,
            negative_results_only=self.negative_results_only,
            temporal_aware=self.temporal_aware,
            patent_overlap=self.patent_overlap,
            grey_literature=self.grey_literature,
            conference_priority=self.conference_priority,
            cited_by_quality_only=self.cited_by_quality_only,
            private_search_vault=self.private_search_vault,
            collaborative_session=self.collaborative_session,
        )


class SavedSearchRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    query: str = Field(min_length=2)
    sources: list[str] = Field(default_factory=list)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    alert_enabled: bool = True
    alert_cadence: Literal["daily", "weekly", "instant"] = "daily"


class SavedSearchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    alert_enabled: bool | None = None
    alert_cadence: Literal["daily", "weekly", "instant"] | None = None


class SavedSearchRecord(BaseModel):
    id: str
    name: str
    query: str
    sources: list[str]
    filters: SearchFilters
    alert_enabled: bool = True
    alert_cadence: str = "daily"
    created_at: str
    last_triggered_at: str | None = None
    new_match_count: int = 0


class SearchAlertPreview(BaseModel):
    saved_search_id: str
    query: str
    cadence: str
    new_match_count: int
    matched_titles: list[str] = Field(default_factory=list)


class SearchHistoryItem(BaseModel):
    session_id: str
    query: str
    normalized_query: str
    sources: list[str]
    created_at: str
    result_count: int
    resumable_url: str


class SearchExportRequest(BaseModel):
    format: Literal["csv", "bibtex"] = "csv"
    papers: list[PaperRecord] = Field(default_factory=list)


class SearchExportResponse(BaseModel):
    format: str
    filename: str
    content: str


class TrendingPaperItem(BaseModel):
    title: str
    source: str
    year: int | None = None
    reason: str


class TrendingSearchResponse(BaseModel):
    topics: list[str] = Field(default_factory=list)
    papers: list[TrendingPaperItem] = Field(default_factory=list)


class SearchWorkspaceSnapshot(BaseModel):
    saved_searches: list[SavedSearchRecord] = Field(default_factory=list)
    history: list[SearchHistoryItem] = Field(default_factory=list)
    alert_previews: list[SearchAlertPreview] = Field(default_factory=list)


class SearchAlertRunResponse(BaseModel):
    user_id: str
    evaluated_count: int
    triggered_count: int
    notifications: list[dict[str, str | int | list[str]]] = Field(default_factory=list)
    generated_at: str
