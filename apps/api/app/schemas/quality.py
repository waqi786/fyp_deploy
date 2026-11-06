from pydantic import BaseModel, Field

from app.schemas.evaluation import EvaluationRequest


class TraceableSentence(BaseModel):
    sentence: str
    supported: bool
    inference_only: bool = False
    source_span: str | None = None


class TraceabilityCheckRequest(BaseModel):
    answer: str
    source_spans: list[str] = Field(default_factory=list)
    retrieved_chunks: list[str] = Field(default_factory=list)


class TraceabilityCheckResponse(BaseModel):
    passed: bool
    coverage: float
    traceable_sentences: list[TraceableSentence] = Field(default_factory=list)
    unsupported_sentences: list[str] = Field(default_factory=list)


class NonFunctionalQualityRequest(BaseModel):
    benchmark: EvaluationRequest
    traceability: TraceabilityCheckRequest
    summary_latency_seconds: float = 0.0
    multimodal_incorrect_rate: float = 0.0
    free_tier_ready: bool = True
    accessibility_features: list[str] = Field(default_factory=list)
    architecture_docs_present: bool = True
    openapi_docs_enabled: bool = True


class QualityMetric(BaseModel):
    name: str
    value: float | str | bool
    target: float | str | bool
    passed: bool


class NonFunctionalQualityResponse(BaseModel):
    metrics: list[QualityMetric] = Field(default_factory=list)
    overall_passed: bool
    summary: str
    cost_posture: list[str] = Field(default_factory=list)
    testing_methodology: list[str] = Field(default_factory=list)
    documentation_artifacts: list[str] = Field(default_factory=list)


class LaunchReadinessCheck(BaseModel):
    name: str
    status: str
    detail: str
    blocking: bool = False


class LaunchReadinessResponse(BaseModel):
    overall_ready: bool
    release_stage: str
    checks: list[LaunchReadinessCheck] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    required_user_inputs: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
