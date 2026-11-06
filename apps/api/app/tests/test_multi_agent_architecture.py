from app.schemas.agents import MultiAgentWorkflowRequest
from app.schemas.paper import PaperRecord
from app.services.agents.orchestrator import AgentOrchestrator


def make_paper(**overrides) -> PaperRecord:
    data = {
        "paper_id": "m1",
        "title": "Hybrid Retrieval Benchmark Dataset",
        "abstract": "We introduce a benchmark dataset, improve F1, and discuss future work. Figure 1: Accuracy curve on benchmark. Table 1: Dataset comparison. E = mc^2.",
        "year": 2025,
        "venue": "AI Systems",
        "citation_count": 81,
        "is_open_access": True,
        "authors": [{"name": "Ali Khan"}],
        "source": "openalex",
    }
    data.update(overrides)
    return PaperRecord(**data)


def test_multi_agent_workflow_runs_planner_search_reading_and_citation() -> None:
    orchestrator = AgentOrchestrator()
    response = orchestrator.run_workflow(
        MultiAgentWorkflowRequest(
            question="Explain this retrieval paper and provide citations.",
            papers=[make_paper(), make_paper(paper_id="m2", title="Dense Retrieval Limits", abstract="This study highlights limitation patterns and future work.")],
            raw_text="We introduce a benchmark dataset. Figure 1: Accuracy curve on benchmark. Table 1: Dataset comparison. E = mc^2. Future work expands multilingual retrieval.",
            citation_contexts=["This result supports earlier work."],
            focus="retrieval",
        )
    )
    assert response.planner.primary_route == "reading"
    assert response.search is not None
    assert response.reading is not None
    assert response.citation is not None
    assert response.state_history[0].state == "planner"
    assert response.reading.summary.tldr
    assert response.reading.extraction.figures
    assert response.citation.bibtex.item_count >= 1


def test_multi_agent_workflow_runs_comparison_and_critique_route() -> None:
    orchestrator = AgentOrchestrator()
    response = orchestrator.run_workflow(
        MultiAgentWorkflowRequest(
            question="Compare these papers and identify contradictions.",
            papers=[
                make_paper(),
                make_paper(
                    paper_id="m2",
                    title="Benchmark Skepticism for Retrieval",
                    abstract="This study underperforms on the benchmark, highlights limitation patterns, and reports p < 0.05.",
                    citation_count=23,
                    authors=[{"name": "John Smith"}],
                ),
            ],
            raw_text="This collection compares retrieval methods and benchmark outcomes.",
            custom_columns=["dataset", "method", "sample size"],
            focus="retrieval",
        )
    )
    assert response.planner.primary_route == "comparison"
    assert response.comparison is not None
    assert response.critique is not None
    assert response.comparison.comparison.rows
    assert response.critique.trust_reports
    assert response.final_answer


def test_multi_agent_workflow_runs_gap_and_writing_routes() -> None:
    orchestrator = AgentOrchestrator()
    gap_response = orchestrator.run_workflow(
        MultiAgentWorkflowRequest(
            question="Find research gaps and future work in multilingual retrieval.",
            papers=[
                make_paper(),
                make_paper(
                    paper_id="m3",
                    title="Multilingual Graph Retrieval Review",
                    abstract="This review surveys multilingual retrieval, future work, and gap analysis in graph settings.",
                    source="arxiv",
                ),
            ],
            raw_text="Future work includes multilingual evaluation and new datasets.",
            focus="multilingual retrieval",
        )
    )
    writing_response = orchestrator.run_workflow(
        MultiAgentWorkflowRequest(
            question="Write a literature review introduction for multilingual retrieval.",
            papers=[make_paper(), make_paper(paper_id="m4", title="Writing Support for Retrieval", abstract="We introduce a writing-oriented retrieval review with benchmark synthesis.")],
            raw_text="This literature review introduces multilingual retrieval and benchmark synthesis.",
            focus="multilingual retrieval",
        )
    )
    assert gap_response.planner.primary_route == "gap"
    assert gap_response.gap is not None
    assert gap_response.gap.report.research_questions
    assert writing_response.planner.primary_route == "writing"
    assert writing_response.writing is not None
    assert writing_response.writing.literature_review.sections
