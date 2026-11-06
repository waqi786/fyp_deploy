from app.schemas.evaluation import EvaluationRequest, EvaluationResponse, MetricStatus


class BaselineEvaluator:
    def evaluate(self, payload: EvaluationRequest) -> EvaluationResponse:
        statuses: list[MetricStatus] = []

        dedup_reduction = 0.0
        if payload.raw_result_count:
            dedup_reduction = max(0.0, (payload.raw_result_count - payload.deduplicated_result_count) / payload.raw_result_count)
        rag_accuracy = self._rag_accuracy(payload)
        summary_score = (sum(payload.summary_scores) / len(payload.summary_scores)) if payload.summary_scores else 0.0
        draft_success_rate = (payload.draft_successes / payload.draft_total) if payload.draft_total else 0.0
        bridge_accuracy = (
            payload.citation_graph_bridge_hits / payload.citation_graph_bridge_total
            if payload.citation_graph_bridge_total
            else 0.0
        )

        statuses.extend(
            [
                MetricStatus(metric="first_result_latency_ms", value=payload.first_result_latency_ms, baseline=1800.0, passed=payload.first_result_latency_ms <= 1800.0),
                MetricStatus(metric="full_search_latency_ms", value=payload.full_search_latency_ms, baseline=9000.0, passed=payload.full_search_latency_ms <= 9000.0),
                MetricStatus(metric="dedup_reduction", value=round(dedup_reduction, 3), baseline=0.38, passed=dedup_reduction >= 0.38),
                MetricStatus(metric="summary_quality_mean", value=round(summary_score, 3), baseline=4.1, passed=summary_score >= 4.1),
                MetricStatus(metric="rag_accuracy", value=round(rag_accuracy, 3), baseline=0.74, passed=rag_accuracy >= 0.74),
                MetricStatus(metric="bridge_accuracy", value=round(bridge_accuracy, 3), baseline=11 / 12, passed=bridge_accuracy >= (11 / 12)),
                MetricStatus(metric="draft_success_rate", value=round(draft_success_rate, 3), baseline=0.9, passed=draft_success_rate >= 0.9),
                MetricStatus(metric="concurrent_users_supported", value=float(payload.concurrent_users_supported), baseline=50.0, passed=payload.concurrent_users_supported >= 50),
            ]
        )

        overall = all(status.passed for status in statuses)
        summary = "Baseline targets matched or exceeded." if overall else "Some baseline targets are still below the required thresholds."
        return EvaluationResponse(statuses=statuses, overall_passed=overall, summary=summary)

    def _rag_accuracy(self, payload: EvaluationRequest) -> float:
        if not payload.rag_cases:
            return 0.0
        correct = 0
        for case in payload.rag_cases:
            generated = (case.generated_answer or "").lower()
            if all(expected.lower() in generated for expected in case.expected_answer_contains):
                correct += 1
        return correct / len(payload.rag_cases)
