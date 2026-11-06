from app.schemas.agents import (
    GapAgentOutput,
    MultiAgentWorkflowRequest,
    SearchAgentOutput,
)
from app.schemas.gap import GapReportRequest
from app.services.agents.templates import AGENT_PROMPT_TEMPLATES
from app.services.gap.detector import GapDetectionService


class GapAgent:
    def __init__(self) -> None:
        self.service = GapDetectionService()

    def run(self, payload: MultiAgentWorkflowRequest, search_output: SearchAgentOutput) -> GapAgentOutput:
        report = self.service.analyze(
            GapReportRequest(
                papers=search_output.top_papers[: max(2, min(20, len(search_output.top_papers)))],
                focus=payload.focus,
                current_year=payload.current_year,
            )
        )
        return GapAgentOutput(
            prompt_template=AGENT_PROMPT_TEMPLATES["gap"],
            retrieval_scope="trend and gap analysis over ranked evidence set",
            report=report,
        )

