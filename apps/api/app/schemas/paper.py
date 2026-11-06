import html
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


def clean_abstract_text(value: str | None, title: str = "") -> str | None:
    if not value:
        return value
    text = html.unescape(value)
    text = re.sub(r"(?i)</?jats:[^>]+>|</?(?:p|div|span|br|strong|em|i|b)[^>]*>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    if title.strip() and text.casefold().startswith(title.strip().casefold()):
        text = text[len(title.strip()):].lstrip(" \t:;,.—–-")
    text = re.sub(r"^\s*(?:abstract|summary)\s*:?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if re.fullmatch(r"research result indexed from [a-z0-9_-]+\.?", text, flags=re.IGNORECASE):
        return None
    return text or None


class PaperRecord(BaseModel):
    paper_id: str
    title: str
    translated_title: str | None = None
    abstract: str | None = None
    translated_abstract: str | None = None
    translation_status: str = "original"
    full_text: str | None = Field(default=None, max_length=1_500_000, exclude=True)
    full_text_status: str = Field(default="not_attempted", exclude=True)
    year: int | None = None
    venue: str | None = None
    publication_type: str | None = None
    doi: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    pdf_urls: list[str] = Field(default_factory=list)
    full_text_source: str | None = Field(default=None, exclude=True)
    full_text_source_url: str | None = Field(default=None, exclude=True)
    parsed_tables: list[dict[str, Any]] = Field(default_factory=list, exclude=True)
    citation_count: int = 0
    reference_count: int = 0
    is_open_access: bool = False
    authors: list[dict[str, Any]] = Field(default_factory=list)
    source: str
    all_sources: list[str] = Field(default_factory=list)
    external_ids: dict[str, str] = Field(default_factory=dict)
    journal_quartile: str | None = None
    study_type: str | None = None
    sample_size: int | None = None
    is_retracted: bool = False
    language: str = "en"
    ranking_score: float = 0.0
    cluster_label: str | None = None
    result_badges: list[str] = Field(default_factory=list)
    micro_summary: str | None = None
    institutions: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    methodologies: list[str] = Field(default_factory=list)
    code_repositories: list[str] = Field(default_factory=list)
    peer_review_status: str = "unknown"
    is_preprint: bool = False
    duplicate_warning: str | None = None
    plagiarism_risk_score: float = 0.0
    author_match_score: float = 0.0
    recommendation_reason: str | None = None
    # Query words found in this paper's title/abstract; the UI turns them into a localized "Why this result".
    matched_terms: list[str] = Field(default_factory=list)

    @field_validator("abstract", mode="before")
    @classmethod
    def normalize_abstract(cls, value: str | None) -> str | None:
        return clean_abstract_text(value)

    @model_validator(mode="after")
    def remove_abstract_title_prefix(self):
        self.abstract = clean_abstract_text(self.abstract, self.title)
        return self


class SearchPagination(BaseModel):
    page: int
    page_size: int
    returned_results: int
    total_pages: int
    has_next_page: bool


class SearchCacheStatus(BaseModel):
    inserted_batches: int = 0
    total_items: int = 0
    cached_at: str | None = None


class RankingExplanation(BaseModel):
    paper_id: str
    semantic_score: float
    keyword_score: float
    citation_bonus: float
    reasons: list[str] = Field(default_factory=list)


class PaperSearchResponse(BaseModel):
    query: str
    normalized_query: str
    query_understanding: dict[str, Any] = Field(default_factory=dict)
    translated_query: str | None = None
    total_results: int
    deduplicated_results: int
    papers: list[PaperRecord]
    translation_retry_ids: list[str] = Field(default_factory=list)
    pagination: SearchPagination
    cache_status: SearchCacheStatus = Field(default_factory=SearchCacheStatus)
    likely_duplicate_pairs: list[list[str]] = Field(default_factory=list)
    source_failures: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    trending_topics: list[str] = Field(default_factory=list)
    clusters: dict[str, list[str]] = Field(default_factory=dict)
    search_mode: str = "hybrid"
    query_type: str = "natural_language"
    interpreted_query: str | None = None
    corrected_query: str | None = None
    boolean_query: str | None = None
    resumable_session_id: str | None = None
    author_network: list[dict[str, Any]] = Field(default_factory=list)
    author_disambiguation: list[dict[str, Any]] = Field(default_factory=list)
    venue_matches: list[str] = Field(default_factory=list)
    institution_matches: list[str] = Field(default_factory=list)
    dataset_matches: list[str] = Field(default_factory=list)
    code_repository_matches: list[str] = Field(default_factory=list)
    recommended_papers: list[dict[str, str]] = Field(default_factory=list)
    citation_expansion_titles: list[str] = Field(default_factory=list)
    co_citation_pairs: list[dict[str, Any]] = Field(default_factory=list)
    bibliographic_coupling_pairs: list[dict[str, Any]] = Field(default_factory=list)
    figure_search_matches: list[dict[str, str]] = Field(default_factory=list)
    source_coverage: dict[str, int] = Field(default_factory=dict)
    search_insights: dict[str, Any] = Field(default_factory=dict)
    ranking_explanations: list[RankingExplanation] = Field(default_factory=list)
    prefetch_next_page: str | None = None
    lazy_prefetch_window: list[str] = Field(default_factory=list)
    alert_preview_available: bool = False
    export_formats: list[str] = Field(default_factory=lambda: ["csv", "bibtex"])
