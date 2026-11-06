from dataclasses import dataclass

from app.schemas.agents import (
    AgentStateTransition,
    MultiAgentWorkflowRequest,
    MultiAgentWorkflowResponse,
)
from app.services.agents.citation_agent import CitationAgent
from app.services.agents.comparison_agent import ComparisonAgent
from app.services.agents.critique_agent import CritiqueTrustAgent
from app.services.agents.gap_agent import GapAgent
from app.services.agents.planner import PlannerAgent
from app.services.agents.reading_agent import ReadingExtractionAgent
from app.services.agents.search_agent import SearchAgent
from app.services.agents.writing_agent import WritingAgent
from app.services.models.adapters import build_llm_adapter

try:
    from app.core.config import settings

    DEFAULT_PROVIDER = settings.default_llm_provider
except Exception:
    DEFAULT_PROVIDER = "groq"


@dataclass
class AgentResult:
    agent: str
    summary: str
    confidence_score: float
    citations: list[str]


class SpecialistAgent:
    def __init__(self, name: str) -> None:
        self.name = name
        self.adapter = build_llm_adapter(DEFAULT_PROVIDER)

    def run(self, question: str) -> AgentResult:
        completion = self.adapter.complete(f"{self.name} specialist request: {question}")
        return AgentResult(
            agent=self.name,
            summary=completion.text,
            confidence_score=completion.confidence,
            citations=[],
        )


class AgentOrchestrator:
    def __init__(self) -> None:
        self.planner = PlannerAgent()
        self.search_agent = SearchAgent()
        self.reading_agent = ReadingExtractionAgent()
        self.comparison_agent = ComparisonAgent()
        self.critique_agent = CritiqueTrustAgent()
        self.gap_agent = GapAgent()
        self.writing_agent = WritingAgent()
        self.citation_agent = CitationAgent()
        self.specialists = {
            "reading": SpecialistAgent("reading"),
            "comparison": SpecialistAgent("comparison"),
            "gap": SpecialistAgent("gap"),
            "writing": SpecialistAgent("writing"),
            "citation": SpecialistAgent("citation"),
            "search": SpecialistAgent("search"),
            "critique": SpecialistAgent("critique"),
            "statistician": SpecialistAgent("statistician"),
            "ethics": SpecialistAgent("ethics"),
        }

    def handle(self, question: str) -> AgentResult:
        route = self.planner.decide(MultiAgentWorkflowRequest(question=question)).primary_route
        return self.specialists[route].run(question)

    def coordinate(self, question: str) -> tuple[list[str], list[AgentResult]]:
        planner = self.planner.decide(MultiAgentWorkflowRequest(question=question))
        plan = [f"Planner selected the {planner.primary_route} route."] + planner.rationale
        selected = [planner.primary_route, "statistician", "ethics"]
        if planner.primary_route != "reading":
            selected.append("writing")
        results = [self.specialists[name].run(question) for name in selected]
        return plan, results

    def run_workflow(self, payload: MultiAgentWorkflowRequest) -> MultiAgentWorkflowResponse:
        history: list[AgentStateTransition] = []
        planner = self.planner.decide(payload)
        self._transition(history, "planner", "completed", f"Primary route: {planner.primary_route}")

        search_output = self.search_agent.run(payload)
        self._transition(history, "search", "completed", f"{search_output.deduplicated_results} deduplicated papers ready.")

        reading_output = self.reading_agent.run(payload, search_output)
        self._transition(history, "reading", "completed", f"{len(reading_output.extraction.figures)} figures and {len(reading_output.extraction.tables)} tables extracted.")

        comparison_output = None
        if "comparison" in planner.specialist_sequence and len(search_output.top_papers) >= 2:
            comparison_output = self.comparison_agent.run(payload, search_output)
            self._transition(history, "comparison", "completed", f"{len(comparison_output.comparison.rows)} rows generated.")

        critique_output = None
        if "critique" in planner.specialist_sequence:
            critique_output = self.critique_agent.run(payload, search_output, reading_output.extraction.extracted_text)
            self._transition(history, "critique", "completed", f"{len(critique_output.trust_reports)} trust reports generated.")

        gap_output = None
        if "gap" in planner.specialist_sequence and len(search_output.top_papers) >= 2:
            gap_output = self.gap_agent.run(payload, search_output)
            self._transition(history, "gap", "completed", f"{len(gap_output.report.research_questions)} research questions generated.")

        writing_output = None
        if "writing" in planner.specialist_sequence:
            writing_output = self.writing_agent.run(payload, reading_output)
            self._transition(history, "writing", "completed", f"{len(writing_output.literature_review.sections)} literature-review sections drafted.")

        citation_output = None
        if "citation" in planner.specialist_sequence and search_output.top_papers:
            citation_output = self.citation_agent.run(payload, search_output)
            self._transition(history, "citation", "completed", f"{citation_output.bibtex.item_count} citations exported.")

        final_answer = self._final_answer(planner.primary_route, reading_output, comparison_output, critique_output, gap_output, writing_output)
        citations = [paper.paper_id for paper in search_output.top_papers[:6]]
        self._transition(history, "finalize", "completed", "Workflow synthesized into a final grounded response.")
        return MultiAgentWorkflowResponse(
            planner=planner,
            state_history=history,
            search=search_output,
            reading=reading_output,
            comparison=comparison_output,
            critique=critique_output,
            gap=gap_output,
            writing=writing_output,
            citation=citation_output,
            final_answer=final_answer,
            citations=citations,
        )

    def _transition(self, history: list[AgentStateTransition], state: str, status: str, note: str) -> None:
        history.append(AgentStateTransition(state=state, status=status, note=note))

    def _final_answer(self, route, reading_output, comparison_output, critique_output, gap_output, writing_output) -> str:
        if route == "comparison" and comparison_output:
            return comparison_output.comparison.narrative_summary
        if route == "gap" and gap_output:
            return gap_output.report.export_markdown
        if route == "writing" and writing_output:
            return writing_output.literature_review.standalone_generators.get("abstract", "")
        critique_note = ""
        if critique_output and critique_output.trust_reports:
            critique_note = f" Trust score snapshot: {critique_output.trust_reports[0].trust_score}."
        return f"{reading_output.summary.tldr}{critique_note}"
