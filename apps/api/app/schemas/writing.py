from pydantic import BaseModel, ConfigDict, Field

from app.schemas.document import ExtractedFigure, ExtractedTable
from app.schemas.entities import TraceableAIOutput


class LiteratureReviewRequest(BaseModel):
    title: str
    extracted_text: str
    figures: list[ExtractedFigure] = Field(default_factory=list)
    tables: list[ExtractedTable] = Field(default_factory=list)
    target_style: str = "ieee"
    citation_style: str = "apa"
    tone: str = "formal"
    mode: str = "literature_review"
    language: str = "en"
    disclosure_watermark: bool = False
    outline_only: bool = False
    section_only: str | None = None
    word_count_target: int = 3500
    section_length_targets: dict[str, int] = Field(default_factory=dict)
    target_journal: str | None = None
    regenerate_instruction: str | None = None
    rollback_to_version: str | None = None
    comments: list[str] = Field(default_factory=list)


class LiteratureReviewSection(TraceableAIOutput):
    title: str
    content: str
    citation_style: str
    word_count: int


class ClaimTrace(TraceableAIOutput):
    sentence: str
    verdict: str
    matched_terms: list[str] = Field(default_factory=list)


class ExportArtifact(BaseModel):
    format: str
    file_name: str
    content: str
    citation_style: str
    generated_at: str
    storage_uri: str | None = None
    content_type: str | None = None
    byte_size: int = 0


class LiteratureReviewResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    outline: list[str]
    sections: dict[str, str]
    section_details: list[LiteratureReviewSection]
    standalone_generators: dict[str, str]
    target_style_adaptation: dict[str, str]
    paragraph_citation_map: list[dict[str, str]]
    citation_style_previews: dict[str, str]
    reference_list: list[str]
    self_critique: dict[str, list[str]]
    critique_trace: list[ClaimTrace]
    plagiarism_report: dict[str, float | str | list[str]]
    readability_score: float
    grammar_notes: list[str]
    academic_style_corrections: list[str]
    transition_suggestions: list[str]
    citation_diversity_nudge: str
    inserted_visuals: list[str]
    figure_table_insertions: list[dict[str, str]]
    export_formats: dict[str, str]
    export_artifacts: list[ExportArtifact]
    overleaf_export: str
    word_count_report: dict[str, int | str]
    section_regeneration: dict[str, str]
    cover_letter: str
    peer_review_response: str
    version_history: list[dict[str, str]]
    rollback_preview: dict[str, str] | None = None
    track_changes: list[dict[str, str]]
    coauthor_comments: list[str]
    watermark: str | None = None
    confidence_score: float
    source_spans: list[str]
    model_used: str
    generated_at: str
