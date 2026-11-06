from pydantic import BaseModel, Field

from app.schemas.paper import PaperRecord


class AdvancedAIRequest(BaseModel):
    question: str
    papers: list[PaperRecord] = Field(default_factory=list)
    language: str = "en"
    mode: str = "answer"
    current_review_paper_ids: list[str] = Field(default_factory=list)
    subscription_query: str | None = None


class EvidenceTrace(BaseModel):
    paper_id: str
    title: str
    support_type: str
    reason: str


class GuardrailDecision(BaseModel):
    rule: str
    outcome: str
    detail: str


class AdvancedAIResponse(BaseModel):
    plan: list[str]
    agent_state_machine: list[dict[str, str]]
    specialist_outputs: dict[str, str]
    final_answer: str
    confidence_score: float
    orchestration_confidence: dict[str, float]
    retrieval_depth: int
    adaptive_retrieval_policy: dict[str, str | int | float]
    grounded_citations: list[str]
    workflow_trace: list[str]
    evidence_trace: list[EvidenceTrace]
    omitted_claims: list[str]
    guardrail_decisions: list[GuardrailDecision]
    zero_hallucination_report: dict[str, str | int | float]
    debate_mode: dict[str, list[str]]
    review_update: dict[str, object]
    auto_review_subscription: dict[str, str | bool]
    review_diff_detail: dict[str, list[str] | str]
    benchmark_summary: list[str]
    benchmark_reasoning_table: list[dict[str, str]]
    explainable_ranking: list[str]
    ranking_explanations: list[dict[str, str | int]]
    critique_panel: dict[str, list[str]]
    perspective_panel: dict[str, list[str]]
    self_critique_summary: dict[str, str | int | float]
    cross_lingual_retrieval_map: list[dict[str, str]]
    translated_evidence: list[str]
    generated_at: str
