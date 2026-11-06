from app.schemas.agents import MultiAgentWorkflowRequest, PlannerDecision
from app.services.agents.templates import AGENT_PROMPT_TEMPLATES


class PlannerAgent:
    def decide(self, payload: MultiAgentWorkflowRequest) -> PlannerDecision:
        lowered = payload.question.lower()
        if any(token in lowered for token in ("compare", "difference", "versus", "vs")):
            route = "comparison"
            sequence = ["search", "reading", "comparison", "critique", "citation"]
            scope = "top 10 deduplicated comparison-ready papers"
            rationale = ["Comparison language detected in the request.", "Structured extraction and trust checks are both needed."]
        elif any(token in lowered for token in ("gap", "trend", "future work", "white space")):
            route = "gap"
            sequence = ["search", "reading", "gap", "critique", "citation"]
            scope = "trend-aware paper cluster across recent and foundational work"
            rationale = ["Gap/trend language detected in the request.", "Trend analysis and contradiction evidence should be surfaced."]
        elif any(token in lowered for token in ("write", "draft", "review", "introduction", "related work")):
            route = "writing"
            sequence = ["search", "reading", "critique", "writing", "citation"]
            scope = "writing-ready evidence set with figures and trust signals"
            rationale = ["Writing-oriented language detected in the request.", "Drafting should happen only after grounded reading and critique."]
        else:
            route = "reading"
            sequence = ["search", "reading", "critique", "citation"]
            scope = "focused evidence set for grounded reading"
            rationale = ["Defaulting to reading route.", "The request primarily asks for understanding rather than synthesis."]
        if payload.citation_contexts:
            sequence.append("citation")
        return PlannerDecision(
            primary_route=route,
            specialist_sequence=list(dict.fromkeys(sequence)),
            retrieval_scope=scope,
            prompt_template=AGENT_PROMPT_TEMPLATES["planner"],
            rationale=rationale,
            confidence_score=0.82,
        )

