from app.schemas.agents import (
    CitationAgentOutput,
    MultiAgentWorkflowRequest,
    SearchAgentOutput,
)
from app.schemas.export import CitationExportRequest
from app.schemas.graph import CitationEdge, CitationGraphRequest, CitationNode
from app.services.agents.templates import AGENT_PROMPT_TEMPLATES
from app.services.exports.citations import CitationExportService
from app.services.graph.metrics import CitationGraphService


class CitationAgent:
    def __init__(self) -> None:
        self.exporter = CitationExportService()
        self.graph = CitationGraphService()

    def run(self, payload: MultiAgentWorkflowRequest, search_output: SearchAgentOutput) -> CitationAgentOutput:
        papers = search_output.top_papers[: max(1, min(10, len(search_output.top_papers)))]
        bibtex = self.exporter.export(CitationExportRequest(papers=papers, format="bibtex"))
        ris = self.exporter.export(CitationExportRequest(papers=papers, format="ris"))
        csljson = self.exporter.export(CitationExportRequest(papers=papers, format="csljson"))
        graph_metrics = self.graph.analyze(self._build_graph_request(papers))
        context_answers = [
            f"Context label: {context}"
            for context in payload.citation_contexts[:5]
        ]
        return CitationAgentOutput(
            prompt_template=AGENT_PROMPT_TEMPLATES["citation"],
            retrieval_scope="citation formatting plus graph-based context analysis",
            bibtex=bibtex,
            ris=ris,
            csljson=csljson,
            citation_context_answers=context_answers,
            graph_metrics=graph_metrics,
        )

    def _build_graph_request(self, papers):
        nodes = [
            CitationNode(paper_id=paper.paper_id, title=paper.title, year=paper.year, citation_count=paper.citation_count)
            for paper in papers
        ]
        edges = []
        for index in range(max(0, len(papers) - 1)):
            edges.append(CitationEdge(source=papers[index + 1].paper_id, target=papers[index].paper_id))
        return CitationGraphRequest(roots=[paper.paper_id for paper in papers[:2]], nodes=nodes, edges=edges)

