from app.schemas.agents import ComparisonAgentOutput, MultiAgentWorkflowRequest, SearchAgentOutput
from app.schemas.comparison import ComparisonRequest
from app.services.agents.templates import AGENT_PROMPT_TEMPLATES
from app.services.comparison.engine import ComparisonEngine


class ComparisonAgent:
    def __init__(self) -> None:
        self.engine = ComparisonEngine()

    def run(self, payload: MultiAgentWorkflowRequest, search_output: SearchAgentOutput) -> ComparisonAgentOutput:
        papers = search_output.top_papers[: max(2, min(10, len(search_output.top_papers)))]
        response = self.engine.compare(
            ComparisonRequest(
                papers=papers,
                focus=payload.focus,
                custom_columns=payload.custom_columns or ["dataset", "method", "sample size"],
            )
        )
        return ComparisonAgentOutput(
            prompt_template=AGENT_PROMPT_TEMPLATES["comparison"],
            retrieval_scope="top deduplicated papers capped for structured comparison",
            comparison=response,
        )

