from app.schemas.agents import CritiqueAgentOutput, MultiAgentWorkflowRequest, SearchAgentOutput
from app.schemas.trust import TrustAnalysisRequest
from app.services.agents.templates import AGENT_PROMPT_TEMPLATES
from app.services.critique.trust import TrustAnalysisService


class CritiqueTrustAgent:
    def __init__(self) -> None:
        self.service = TrustAnalysisService()

    def run(self, payload: MultiAgentWorkflowRequest, search_output: SearchAgentOutput, full_text: str) -> CritiqueAgentOutput:
        trust_reports = []
        contradictions = []
        papers = search_output.top_papers[:4]
        for paper in papers:
            response = self.service.analyze(
                TrustAnalysisRequest(
                    paper=paper,
                    full_text=full_text,
                    peer_reviewed=paper.source.lower() not in {"arxiv", "preprint"},
                    citation_contexts=payload.citation_contexts,
                    related_papers=[candidate for candidate in papers if candidate.paper_id != paper.paper_id],
                )
            )
            trust_reports.append(response)
            contradictions.extend(response.contradiction_summary)
        return CritiqueAgentOutput(
            prompt_template=AGENT_PROMPT_TEMPLATES["critique"],
            retrieval_scope="paper-level trust analysis over ranked evidence",
            trust_reports=trust_reports,
            contradiction_rollup=list(dict.fromkeys(contradictions)),
        )

