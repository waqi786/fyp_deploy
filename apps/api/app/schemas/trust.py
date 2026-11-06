from pydantic import BaseModel, Field

from app.schemas.paper import PaperRecord


class TrustAnalysisRequest(BaseModel):
    paper: PaperRecord
    full_text: str | None = None
    peer_reviewed: bool | None = None
    citation_contexts: list[str] = Field(default_factory=list)
    related_papers: list[PaperRecord] = Field(default_factory=list)
    manual_flag_as_questionable: bool = False
    moderation_note: str | None = None


class TrustSignal(BaseModel):
    label: str
    value: str
    impact: str
    evidence: str | None = None
    score_delta: float | None = None


class TrustChecklistItem(BaseModel):
    label: str
    passed: bool
    explanation: str


class JournalImpactProfile(BaseModel):
    quartile: str | None = None
    impact_tier: str
    citation_signal: str


class CitationContextLabel(BaseModel):
    context: str
    label: str


class BiasTagDetail(BaseModel):
    label: str
    explanation: str


class StatisticalSanityCheck(BaseModel):
    label: str
    status: str
    evidence: str | None = None


class EvidenceMeterEntry(BaseModel):
    label: str
    score: float
    explanation: str


class SampleSizeProfile(BaseModel):
    extracted_n: int
    adequacy: str
    explanation: str


class TrustChangeLogEntry(BaseModel):
    event: str
    score_delta: float
    reason: str
    evidence: str | None = None


class ContradictionDetail(BaseModel):
    summary: str
    focal_paper_id: str
    related_paper_id: str
    supporting_evidence: list[str] = Field(default_factory=list)


class ModerationQueueEntry(BaseModel):
    status: str
    reason: str
    note: str | None = None
    evidence: list[str] = Field(default_factory=list)


class TrustAnalysisResponse(BaseModel):
    trust_score: float
    novelty_score: float
    evidence_strength: str
    confidence_score: float
    peer_review_status: str
    journal_quartile: str | None = None
    journal_impact_profile: JournalImpactProfile
    retraction_check: str
    erratum_check: str
    conflict_of_interest_flag: str
    funding_transparency_flag: str
    author_track_record_summary: str
    self_citation_ratio: float
    self_citation_flag: str
    sample_size_adequacy: str
    sample_size_profile: SampleSizeProfile
    effect_size: str
    reproducibility_score: float
    replication_outlook: str
    statistical_appropriateness: str
    contradiction_summary: list[str] = Field(default_factory=list)
    contradiction_details: list[ContradictionDetail] = Field(default_factory=list)
    bias_tags: list[str] = Field(default_factory=list)
    bias_tag_details: list[BiasTagDetail] = Field(default_factory=list)
    outlier_anomaly_flags: list[str] = Field(default_factory=list)
    ci_pvalue_sanity: list[str] = Field(default_factory=list)
    statistical_sanity_checks: list[StatisticalSanityCheck] = Field(default_factory=list)
    methodology_quality_checklist: list[TrustChecklistItem] = Field(default_factory=list)
    evidence_strength_breakdown: dict[str, float] = Field(default_factory=dict)
    evidence_meter: list[EvidenceMeterEntry] = Field(default_factory=list)
    score_trace: dict[str, float] = Field(default_factory=dict)
    citation_context_labels: list[CitationContextLabel] = Field(default_factory=list)
    moderation_status: str = "clean"
    moderation_queue_entry: ModerationQueueEntry | None = None
    trust_score_changelog: list[TrustChangeLogEntry] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    green_flags: list[str] = Field(default_factory=list)
    signals: list[TrustSignal] = Field(default_factory=list)
