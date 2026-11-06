from app.schemas.quality import NonFunctionalQualityRequest, NonFunctionalQualityResponse, QualityMetric
from app.services.evaluation.benchmark import BaselineEvaluator
from app.services.quality.traceability import TraceabilityGuardService


class NonFunctionalQualityService:
    def __init__(self) -> None:
        self.baseline = BaselineEvaluator()
        self.traceability = TraceabilityGuardService()

    def assess(self, payload: NonFunctionalQualityRequest) -> NonFunctionalQualityResponse:
        trace = self.traceability.validate(payload.traceability)
        rag_accuracy = self._metric_value(payload.benchmark, "rag_accuracy")
        dedup_reduction = self._metric_value(payload.benchmark, "dedup_reduction")
        first_latency = payload.benchmark.first_result_latency_ms
        full_latency = payload.benchmark.full_search_latency_ms
        concurrent = payload.benchmark.concurrent_users_supported

        metrics = [
            QualityMetric(name="traceability_coverage", value=trace.coverage, target=1.0, passed=trace.passed and trace.coverage >= 0.95),
            QualityMetric(name="first_result_latency_ms", value=first_latency, target=1600.0, passed=first_latency > 0 and first_latency <= 1600.0),
            QualityMetric(name="full_search_latency_ms", value=full_latency, target=6000.0, passed=full_latency > 0 and full_latency <= 6000.0),
            QualityMetric(name="rag_accuracy", value=rag_accuracy, target=0.80, passed=rag_accuracy >= 0.80),
            QualityMetric(name="dedup_reduction", value=dedup_reduction, target=0.42, passed=dedup_reduction >= 0.42),
            QualityMetric(name="summary_latency_seconds", value=payload.summary_latency_seconds, target=15.0, passed=payload.summary_latency_seconds > 0 and payload.summary_latency_seconds <= 15.0),
            QualityMetric(name="multimodal_incorrect_rate", value=payload.multimodal_incorrect_rate, target=0.05, passed=payload.multimodal_incorrect_rate <= 0.05),
            QualityMetric(name="concurrent_users_supported", value=float(concurrent), target=50.0, passed=concurrent >= 50),
            QualityMetric(name="free_tier_ready", value=payload.free_tier_ready, target=True, passed=payload.free_tier_ready is True),
            QualityMetric(name="openapi_docs_enabled", value=payload.openapi_docs_enabled, target=True, passed=payload.openapi_docs_enabled is True),
            QualityMetric(name="architecture_docs_present", value=payload.architecture_docs_present, target=True, passed=payload.architecture_docs_present is True),
            QualityMetric(
                name="wcag_21_aa_support",
                value="; ".join(payload.accessibility_features),
                target="WCAG 2.1 AA minimum",
                passed={"keyboard navigation", "screen reader labels", "high contrast", "rtl support"}.issubset(set(feature.lower() for feature in payload.accessibility_features)),
            ),
        ]
        overall = all(metric.passed for metric in metrics)
        summary = "Non-functional targets exceed the documented baseline." if overall else "Some non-functional targets still need improvement to beat the documented baseline."
        return NonFunctionalQualityResponse(
            metrics=metrics,
            overall_passed=overall,
            summary=summary,
            cost_posture=[
                "Groq default adapter for LLM inference",
                "FAISS-style local vector retrieval without paid Pinecone requirement",
                "Supabase free-tier compatible auth and Postgres model",
                "Redis-style cache abstraction aligned to Upstash free tier",
            ],
            testing_methodology=[
                "Blind expert scoring for summary quality",
                "Correctness-rate testing for RAG and multimodal failure modes",
                "Manual and automated load testing with 50+ concurrent users target",
                "Unit and integration tests enforced in CI",
            ],
            documentation_artifacts=[
                "/docs OpenAPI UI",
                "docs/architecture-six-layers.md",
                "docs/non-functional-requirements.md",
            ],
        )

    def _metric_value(self, benchmark, name: str) -> float:
        result = self.baseline.evaluate(benchmark)
        for status in result.statuses:
            if status.metric == name:
                return status.value
        return 0.0

