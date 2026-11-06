from app.schemas.chat import ChatDocument
from app.schemas.evaluation import EvaluationCase, EvaluationRequest
from app.schemas.quality import NonFunctionalQualityRequest, TraceabilityCheckRequest
from app.services.quality.launch_readiness import LaunchReadinessService
from app.services.quality.requirements import NonFunctionalQualityService
from app.services.quality.traceability import TraceabilityGuardService
from app.services.retrieval.chat_engine import GroundedChatEngine


def test_traceability_guard_flags_unsupported_sentences() -> None:
    service = TraceabilityGuardService()
    response = service.validate(
        TraceabilityCheckRequest(
            answer="Paper p1 reports benchmark gains. This system cures every disease. AI inference, not from source: ranking was adjusted.",
            source_spans=["p1: Paper p1 reports benchmark gains on the retrieval benchmark."],
            retrieved_chunks=["Paper p1 reports benchmark gains on the retrieval benchmark."],
        )
    )
    assert response.coverage >= 0.5
    assert any("cures every disease" in sentence for sentence in response.unsupported_sentences)
    assert response.traceable_sentences[-1].inference_only is True


def test_grounded_chat_returns_traceability_metadata() -> None:
    engine = GroundedChatEngine()
    response = engine.answer(
        "What does the paper say about benchmark gains?",
        [
            ChatDocument(
                paper_id="p1",
                title="Benchmark Paper",
                content="This paper reports benchmark gains and grounded evidence.",
            )
        ],
        show_your_work=True,
    )
    assert response.traceable_sentences
    assert response.traceability_coverage > 0
    assert response.traceability_passed is True


def test_non_functional_quality_service_assesses_stronger_targets() -> None:
    service = NonFunctionalQualityService()
    response = service.assess(
        NonFunctionalQualityRequest(
            benchmark=EvaluationRequest(
                summary_scores=[4.4, 4.5, 4.6],
                rag_cases=[EvaluationCase(case_id="1", question="Q", expected_answer_contains=["hybrid"], generated_answer="hybrid grounded answer")],
                draft_successes=10,
                draft_total=10,
                citation_graph_bridge_hits=11,
                citation_graph_bridge_total=12,
                first_result_latency_ms=1500,
                full_search_latency_ms=5800,
                raw_result_count=100,
                deduplicated_result_count=55,
                concurrent_users_supported=60,
            ),
            traceability=TraceabilityCheckRequest(
                answer="p1 reports hybrid gains.",
                source_spans=["p1: p1 reports hybrid gains."],
                retrieved_chunks=["p1 reports hybrid gains."],
            ),
            summary_latency_seconds=11.5,
            multimodal_incorrect_rate=0.04,
            free_tier_ready=True,
            accessibility_features=["keyboard navigation", "screen reader labels", "high contrast", "rtl support"],
            architecture_docs_present=True,
            openapi_docs_enabled=True,
        )
    )
    assert response.overall_passed is True
    assert any(metric.name == "traceability_coverage" and metric.passed for metric in response.metrics)
    assert any(metric.name == "full_search_latency_ms" and metric.passed for metric in response.metrics)
    assert any(metric.name == "free_tier_ready" and metric.passed for metric in response.metrics)


def test_launch_readiness_service_flags_blocking_production_gaps() -> None:
    service = LaunchReadinessService()
    response = service.audit()
    assert response.release_stage in {"private_beta_only", "public_launch"}
    assert response.checks
    assert response.required_user_inputs
    assert any(check.name == "known_platform_gap" and check.blocking for check in response.checks)
