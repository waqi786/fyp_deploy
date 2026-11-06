from pydantic import BaseModel, Field


class EvaluationCase(BaseModel):
    case_id: str
    question: str
    expected_answer_contains: list[str] = Field(default_factory=list)
    generated_answer: str | None = None
    confidence_score: float | None = None


class EvaluationRequest(BaseModel):
    summary_scores: list[float] = Field(default_factory=list)
    rag_cases: list[EvaluationCase] = Field(default_factory=list)
    draft_successes: int = 0
    draft_total: int = 0
    citation_graph_bridge_hits: int = 0
    citation_graph_bridge_total: int = 0
    first_result_latency_ms: float = 0.0
    full_search_latency_ms: float = 0.0
    raw_result_count: int = 0
    deduplicated_result_count: int = 0
    concurrent_users_supported: int = 0


class MetricStatus(BaseModel):
    metric: str
    value: float
    baseline: float
    passed: bool


class EvaluationResponse(BaseModel):
    statuses: list[MetricStatus]
    overall_passed: bool
    summary: str
