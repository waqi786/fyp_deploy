from pydantic import BaseModel, Field


class VerificationMetric(BaseModel):
    name: str
    measured_value: float | str
    baseline_value: float | str
    better_than_baseline: bool


class VerificationSample(BaseModel):
    input_summary: str
    output_summary: str


class PhaseVerificationReport(BaseModel):
    phase_order: int
    phase_title: str
    status: str
    sample: VerificationSample
    metrics: list[VerificationMetric] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class VerificationReportResponse(BaseModel):
    project: str
    reports: list[PhaseVerificationReport] = Field(default_factory=list)


class FeatureVerificationItem(BaseModel):
    feature_key: str
    feature_name: str
    category: str = "General"
    status: str
    enforcement_status: str = "DONE"
    evidence: str
    user_flow: str
    route: str = "/"
    automated_check: str = "smoke"
    verification_command: str = "python -m pytest app/tests -q"
    acceptance_criteria_count: int = 0
    capabilities: list[str] = Field(default_factory=list)
    production_notes: list[str] = Field(default_factory=list)
    blocking: bool = False


class FeatureVerificationResponse(BaseModel):
    project: str
    summary: str
    total_features_checked: int
    passed_count: int
    pending_count: int
    items: list[FeatureVerificationItem] = Field(default_factory=list)


class ProposalObjectiveItem(BaseModel):
    objective_key: str
    proposal_text: str
    implementation_status: str
    product_route: str
    verification_check: str
    evidence: str
    caveats: list[str] = Field(default_factory=list)


class ProposalAlignmentResponse(BaseModel):
    project: str
    source_document: str
    summary: str
    readiness_score: int
    completed_count: int
    partial_count: int
    pending_count: int
    objectives: list[ProposalObjectiveItem] = Field(default_factory=list)


class CompleteFeatureChecklistItem(BaseModel):
    feature_id: str
    module: str
    title: str
    implementation_status: str
    production_status: str
    mapped_route: str
    verification_check: str
    evidence: str
    remediation: str | None = None


class CompleteFeatureChecklistResponse(BaseModel):
    project: str
    source_document: str
    total_features: int
    implemented_count: int
    partial_count: int
    pending_count: int
    production_ready_count: int
    production_gap_count: int
    summary: str
    items: list[CompleteFeatureChecklistItem] = Field(default_factory=list)


class CommittedScopeItem(BaseModel):
    item_number: int
    title: str
    phase: str
    status_label: str
    product_route: str
    evidence: str
    verification_command: str
    unhappy_path: str
    blocking: bool = False


class ScopeGuardrailItem(BaseModel):
    rule: str
    status_label: str
    evidence: str
    action: str


class CommittedScopeResponse(BaseModel):
    project: str
    source_document: str
    summary: str
    done_count: int
    partial_count: int
    blocked_count: int
    out_of_scope_items: list[str] = Field(default_factory=list)
    guardrails: list[ScopeGuardrailItem] = Field(default_factory=list)
    items: list[CommittedScopeItem] = Field(default_factory=list)
