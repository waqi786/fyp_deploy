from app.schemas.chat import ChatCitationEdge, ChatDocument
from app.schemas.gap import GapReportRequest
from app.schemas.paper import PaperRecord
from app.services.gap.detector import GapDetectionService
from app.services.retrieval.chat_engine import GroundedChatEngine


def make_paper(**overrides) -> PaperRecord:
    data = {
        "paper_id": "g1",
        "title": "Multimodal Retrieval Benchmark",
        "abstract": "We introduce a benchmark dataset and improve retrieval. Future work explores multilingual deployment.",
        "year": 2025,
        "venue": "AI Journal",
        "citation_count": 40,
        "is_open_access": True,
        "authors": [{"name": "Ali Khan"}],
        "source": "arxiv",
    }
    data.update(overrides)
    return PaperRecord(**data)


def test_gap_detection_returns_trend_signals() -> None:
    service = GapDetectionService()
    result = service.analyze(
        GapReportRequest(
            papers=[
                make_paper(),
                make_paper(
                    paper_id="g2",
                    title="Graph Clinical Benchmark",
                    abstract="This benchmark reports limitations in clinical graph retrieval and underperforms in noisy settings.",
                    year=2024,
                    authors=[{"name": "John Smith"}],
                ),
                make_paper(
                    paper_id="g3",
                    title="Education RAG Review",
                    abstract="This review surveys retrieval and dataset usage across education systems.",
                    year=2023,
                    source="openalex",
                ),
            ],
            focus="retrieval",
        )
    )
    assert result.white_space_map
    assert result.unstudied_combinations
    assert result.white_space_visual_map
    assert result.white_space_map[0].supporting_paper_ids
    assert result.future_work_suggestions
    assert result.future_work_suggestions[0].evidence
    assert result.publication_volume_trend
    assert result.publication_volume_chart
    assert result.trend_summary["publication_volume_trend"]
    assert result.contradiction_evidence
    assert result.contradiction_evidence[0].supporting_evidence
    assert result.research_questions
    assert result.method_adoption_chart
    assert result.dataset_popularity_trend
    assert result.institutional_distribution_map
    assert result.funding_trend_correlation
    assert result.coauthorship_network_evolution
    assert result.cross_disciplinary_gaps
    assert result.underexplored_population_flags
    assert result.benchmark_saturation
    assert result.recent_preprint_details
    assert result.export_markdown
    assert result.export_csv
    assert "\"white_space_map\"" in result.export_json
    assert result.generated_at


def test_chat_extensions_support_citation_context_and_export() -> None:
    engine = GroundedChatEngine()
    response = engine.answer(
        "Why does this paper cite the earlier work?",
        [
            ChatDocument(
                paper_id="p1",
                title="Primary Paper",
                content="This paper improves retrieval using benchmark evidence.",
            )
        ],
        session_id="thread-1",
        conversation_history=["Tell me about Primary Paper."],
        citation_edges=[
            ChatCitationEdge(
                source_paper_id="p1",
                target_paper_id="p0",
                context="supports earlier evidence on benchmark stability",
                sentiment="support",
            )
        ],
    )
    assert response.condensed_question
    assert response.citation_context_answers
    assert response.inline_citations
    assert response.highlighted_source_spans
    assert response.citation_sentiment_labels[0]["sentiment"] == "support"
    assert response.chat_scope == "single-paper"
    assert response.automatic_literature_suggestions
    assert response.shareable_thread_token
    assert response.session_turns == 1
    assert response.generated_at


def test_chat_fallback_marks_reason_when_documents_missing() -> None:
    engine = GroundedChatEngine()
    response = engine.answer("Summarize this paper", [], session_id="empty-session")
    assert response.fallback_reason == "NO_DOCUMENTS"
    assert response.chat_scope == "none"
    assert response.voice_output_text
    assert response.session_turns == 0
