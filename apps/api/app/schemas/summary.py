from pydantic import BaseModel, ConfigDict, Field


class SummaryRequest(BaseModel):
    title: str
    content: str
    language: str = "en"
    audience: str = "expert"
    summary_length: str = "medium"
    target_languages: list[str] = Field(default_factory=lambda: ["ur", "es", "fr", "de", "ar", "tr", "zh", "hi", "fa", "id"])


class SummaryTier(BaseModel):
    label: str
    content: str
    source_spans: list[str] = Field(default_factory=list)


class GlossaryEntry(BaseModel):
    term: str
    definition: str
    source_span: str


class GlossaryHoverSpan(BaseModel):
    term: str
    definition: str
    start_offset: int
    end_offset: int


class OutlineSectionDetail(BaseModel):
    label: str
    source_span: str


class SummaryResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    tldr: str
    bullet_summary: list[str]
    structured_summary: dict[str, str]
    deep_dive: str
    summary_tiers: dict[str, SummaryTier]
    equations: list[str]
    urdu_summary: dict[str, str]
    glossary: dict[str, str]
    glossary_entries: list[GlossaryEntry]
    hover_glossary_spans: list[GlossaryHoverSpan]
    difficulty_score: str
    prerequisites: list[str]
    contributions: list[str]
    limitations: list[str]
    methodology_box: str
    results_box: str
    datasets: list[str]
    reproducibility_checklist: dict[str, bool]
    funding_or_coi: list[str]
    freshness_indicator: str
    related_work_summary: str
    auto_outline: list[str]
    outline_sections: list[OutlineSectionDetail]
    reading_time_minutes: int
    key_figure_caption: str | None = None
    acronym_expansions: dict[str, str]
    statistical_flags: list[str]
    study_limitation_severity_score: float
    exam_qa: list[dict[str, str]]
    translations: dict[str, dict[str, str | list[str]]]
    translation_languages: list[str]
    audio_narration: dict[str, str]
    audience_mode: str
    audience_guidance: str
    summary_length_applied: str
    paragraph_explainability_preview: list[dict[str, str | list[str]]]
    key_figure_insight: str | None = None
    confidence_score: float
    model_used: str
    source_spans: list[str] = Field(default_factory=list)
    generated_at: str
    fallback_used: bool = False


class ParagraphExplainRequest(BaseModel):
    title: str
    paragraph: str
    audience: str = "beginner"
    language: str = "en"


class ParagraphExplainResponse(BaseModel):
    explanation: str
    simplified_points: list[str]
    glossary_terms: dict[str, str]
    audience_mode: str
    reading_level: str
    source_span: str
    confidence_score: float
    model_used: str
