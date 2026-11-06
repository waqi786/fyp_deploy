from app.schemas.chat import ChatCitationEdge, ChatDocument, ChatFigure, ChatTable
from app.schemas.evaluation import EvaluationCase, EvaluationRequest
from app.services.evaluation.benchmark import BaselineEvaluator
from app.services.retrieval.chat_benchmark import (
    ChatBenchmarkCase,
    ChatBenchmarkService,
)
from app.services.retrieval.chat_engine import GroundedChatEngine


def test_multimodal_chat_uses_figure_table_equation_context() -> None:
    engine = GroundedChatEngine()
    response = engine.answer(
        "What does Figure 1 show and which equation is referenced?",
        [
            ChatDocument(
                paper_id="p1",
                title="Vision Paper",
                content="The paper studies retrieval quality.",
                figures=[ChatFigure(figure_id="1", caption="Figure 1: Accuracy increases over epochs", description="Accuracy trend")],
                tables=[ChatTable(table_id="1", caption="Table 1: Benchmark scores", summary="Hybrid RAG wins on F1")],
                equations=["E = mc^2"],
                code_snippets=["def score(answer): return answer.confidence"],
            )
        ],
        session_id="s1",
        conversation_history=["Tell me about the paper."],
        show_your_work=True,
        citation_edges=[ChatCitationEdge(source_paper_id="p1", target_paper_id="p2", context="supports earlier evidence", sentiment="support")],
    )
    assert response.retrieval_mode == "text+multimodal"
    assert response.citations == ["p1"]
    assert "Multimodal evidence" in response.answer
    assert response.follow_up_suggestions
    assert response.automatic_literature_suggestions
    assert response.inline_citations
    assert response.highlighted_source_spans
    assert response.chat_scope == "single-paper"
    assert response.voice_output_text
    assert response.retrieved_chunks
    assert response.feedback_token
    assert response.export_markdown
    assert response.retrieval_mode == "text+multimodal"
    assert response.fallback_reason is None
    assert response.generated_at


def test_chat_benchmark_shows_multimodal_at_least_as_good_as_text_only() -> None:
    report = ChatBenchmarkService().evaluate(
        [
            ChatBenchmarkCase(
                question="What does Figure 1 show and which equation is referenced?",
                expected_substrings=["multimodal evidence", "equation evidence"],
                documents=[
                    ChatDocument(
                        paper_id="p1",
                        title="Vision Paper",
                        content="The paper studies retrieval quality.",
                        figures=[ChatFigure(figure_id="1", caption="Figure 1: Accuracy increases over epochs", description="Accuracy trend")],
                        tables=[ChatTable(table_id="1", caption="Table 1: Benchmark scores", summary="Hybrid RAG wins on F1")],
                        equations=["E = mc^2"],
                    )
                ],
            )
        ]
    )
    by_mode = {item.mode: item for item in report}
    assert by_mode["multimodal"].accuracy >= by_mode["text_only"].accuracy
    assert by_mode["multimodal"].hits == by_mode["multimodal"].total


def test_baseline_evaluator_reports_statuses() -> None:
    evaluator = BaselineEvaluator()
    result = evaluator.evaluate(
        EvaluationRequest(
            summary_scores=[4.2, 4.3, 4.1],
            rag_cases=[EvaluationCase(case_id="1", question="Q", expected_answer_contains=["hybrid"], generated_answer="hybrid retrieval answer")],
            draft_successes=9,
            draft_total=10,
            citation_graph_bridge_hits=11,
            citation_graph_bridge_total=12,
            first_result_latency_ms=1500,
            full_search_latency_ms=7000,
            raw_result_count=100,
            deduplicated_result_count=60,
            concurrent_users_supported=50,
        )
    )
    assert result.statuses
    assert any(status.metric == "dedup_reduction" and status.passed for status in result.statuses)
