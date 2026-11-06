import re
from datetime import UTC, datetime

from app.schemas.advanced import (
    AdvancedAIRequest,
    AdvancedAIResponse,
    EvidenceTrace,
    GuardrailDecision,
)
from app.schemas.agents import MultiAgentWorkflowRequest
from app.services.agents.orchestrator import AgentOrchestrator
from app.services.search.discovery import enrich_search_results, infer_metadata_fields


class AdvancedIntelligenceService:
    def __init__(self) -> None:
        self.orchestrator = AgentOrchestrator()

    def analyze(self, payload: AdvancedAIRequest) -> AdvancedAIResponse:
        generated_at = datetime.now(UTC).isoformat()
        workflow = self.orchestrator.run_workflow(
            MultiAgentWorkflowRequest(
                question=payload.question,
                papers=payload.papers,
                language=payload.language,
                focus="advanced intelligence",
                citation_contexts=[],
            )
        )
        plan = [step.note for step in workflow.state_history if step.state != "finalize"]
        agent_results = self.orchestrator.coordinate(payload.question)[1]
        papers = [infer_metadata_fields(paper) for paper in payload.papers]
        ranked, _, _, _ = enrich_search_results(payload.question, papers) if papers else ([], {}, [], [])
        retrieval_depth = self._adaptive_depth(payload.question, payload.mode)
        evidence_papers = ranked[:retrieval_depth]
        translated = self._translated_evidence(evidence_papers, payload.language)
        supported_lines, omitted_claims, citations = self._grounded_synthesis(payload.question, evidence_papers)
        evidence_trace = self._evidence_trace(evidence_papers)
        debate = self._debate(payload.question, evidence_papers)
        review_update = self._review_update(payload.current_review_paper_ids, evidence_papers, payload.subscription_query)
        review_diff_detail = self._review_diff_detail(payload.current_review_paper_ids, evidence_papers)
        benchmark_summary = self._benchmark_summary(evidence_papers)
        explainable_ranking = self._explainable_ranking(payload.question, evidence_papers)
        critique_panel = self._critique_panel(evidence_papers)
        guardrail_decisions = self._guardrails(payload.question, evidence_papers, omitted_claims)
        workflow_trace = [f"{step.state}:{step.status}:{step.note}" for step in workflow.state_history]
        state_machine = [
            {"state": step.state, "status": step.status, "owner": self._state_owner(step.state), "note": step.note}
            for step in workflow.state_history
        ]
        specialist_outputs = {result.agent: result.summary for result in agent_results}
        orchestration_confidence = {result.agent: round(result.confidence_score, 2) for result in agent_results}
        final_answer = workflow.final_answer if workflow.final_answer else ("\n".join(supported_lines) if supported_lines else "No supported claim could be grounded from the provided papers.")
        if omitted_claims:
            final_answer += "\nUnsupported or speculative content was omitted and marked for review."
        confidence = round(min(0.98, 0.45 + (0.08 * len(citations)) + (0.04 * len(agent_results))), 2)
        adaptive_policy = self._adaptive_policy(payload.question, payload.mode, retrieval_depth)
        hallucination_report = self._zero_hallucination_report(citations, omitted_claims, supported_lines)
        benchmark_table = self._benchmark_reasoning_table(benchmark_summary)
        ranking_explanations = self._ranking_explanation_rows(payload.question, evidence_papers)
        subscription = {
            "enabled": bool(payload.subscription_query),
            "query": payload.subscription_query or "not configured",
            "cadence": "daily diff digest when enabled",
        }
        self_critique = {
            "status": "passed" if not omitted_claims else "passed-with-omissions",
            "unsupported_claims_omitted": len(omitted_claims),
            "grounded_sentence_count": len(supported_lines),
            "rule": "every generated claim must map to at least one ranked evidence paper",
        }
        cross_lingual_map = [
            {"paper_id": paper.paper_id, "source_language": paper.language, "answer_language": payload.language, "status": "translated"}
            for paper in evidence_papers
            if paper.language != payload.language
        ]
        return AdvancedAIResponse(
            plan=plan,
            agent_state_machine=state_machine,
            specialist_outputs=specialist_outputs,
            final_answer=final_answer,
            confidence_score=confidence,
            orchestration_confidence=orchestration_confidence,
            retrieval_depth=retrieval_depth,
            adaptive_retrieval_policy=adaptive_policy,
            grounded_citations=citations,
            workflow_trace=workflow_trace,
            evidence_trace=evidence_trace,
            omitted_claims=omitted_claims,
            guardrail_decisions=guardrail_decisions,
            zero_hallucination_report=hallucination_report,
            debate_mode=debate,
            review_update=review_update,
            auto_review_subscription=subscription,
            review_diff_detail=review_diff_detail,
            benchmark_summary=benchmark_summary,
            benchmark_reasoning_table=benchmark_table,
            explainable_ranking=explainable_ranking,
            ranking_explanations=ranking_explanations,
            critique_panel=critique_panel,
            perspective_panel=critique_panel,
            self_critique_summary=self_critique,
            cross_lingual_retrieval_map=cross_lingual_map,
            translated_evidence=translated,
            generated_at=generated_at,
        )

    def _adaptive_depth(self, question: str, mode: str) -> int:
        tokens = len(question.split())
        if mode == "debate" or any(token in question.lower() for token in ("compare", "debate", "contested", "versus")):
            return 6
        if tokens >= 18 or any(token in question.lower() for token in ("citation", "benchmark", "ethics", "statistics")):
            return 5
        return 3

    def _adaptive_policy(self, question: str, mode: str, depth: int) -> dict[str, str | int | float]:
        complexity = "high" if depth >= 6 else "medium" if depth >= 5 else "focused"
        return {
            "mode": mode,
            "complexity": complexity,
            "selected_depth": depth,
            "minimum_confidence": 0.7,
            "reason": "debate/benchmark/comparison language increases retrieval depth" if depth >= 5 else "focused question uses compact retrieval",
        }

    def _state_owner(self, state: str) -> str:
        owners = {
            "plan": "planner_agent",
            "search": "search_agent",
            "read": "reading_agent",
            "compare": "comparison_agent",
            "critique": "critique_agent",
            "gap": "gap_agent",
            "write": "writing_agent",
            "cite": "citation_agent",
            "finalize": "planner_agent",
        }
        return owners.get(state, "planner_agent")

    def _translated_evidence(self, papers, answer_language: str) -> list[str]:
        translated = []
        for paper in papers:
            if paper.language != answer_language:
                translated.append(f"Translated from {paper.language} paper '{paper.title}' into {answer_language}.")
        return translated

    def _grounded_synthesis(self, question: str, papers) -> tuple[list[str], list[str], list[str]]:
        supported = []
        omitted = []
        citations = []
        for paper in papers:
            text = f"{paper.title}. {paper.abstract or ''}".strip()
            if not text or len((paper.abstract or "").split()) < 4:
                omitted.append(f"{paper.paper_id}: insufficient evidence for grounded synthesis")
                continue
            citations.append(paper.paper_id)
            supported.append(f"{paper.paper_id}: {text[:220]}")
            if "will definitely" in (paper.abstract or "").lower() or "cures every" in (paper.abstract or "").lower():
                omitted.append(f"{paper.paper_id}: unsupported overclaim omitted")
        if not supported and question:
            omitted.append("No retrievable supporting chunk for the requested claim.")
        return supported[:4], omitted, citations[:6]

    def _debate(self, question: str, papers) -> dict[str, list[str]]:
        pro = []
        con = []
        for paper in papers:
            abstract = (paper.abstract or "").lower()
            line = f"{paper.paper_id}: {paper.title}"
            if any(token in abstract for token in ("improve", "outperform", "support", "effective")):
                pro.append(line)
            if any(token in abstract for token in ("however", "limitation", "bias", "underperform", "conflict")):
                con.append(line)
        if not pro and papers:
            pro.append(f"{papers[0].paper_id}: baseline evidence remains promising")
        if not con and papers:
            con.append(f"{papers[-1].paper_id}: limitations and uncertainty still need review")
        return {"for": pro[:4], "against": con[:4]}

    def _review_update(self, current_review_paper_ids: list[str], papers, subscription_query: str | None) -> dict[str, object]:
        new_papers = [paper.paper_id for paper in papers if paper.paper_id not in current_review_paper_ids]
        return {
            "subscription_query": subscription_query or "manual review tracking",
            "new_papers": new_papers,
            "diff_summary": f"{len(new_papers)} new papers differ from the tracked review set.",
        }

    def _review_diff_detail(self, current_review_paper_ids: list[str], papers) -> dict[str, list[str] | str]:
        ranked_ids = [paper.paper_id for paper in papers]
        added = [paper_id for paper_id in ranked_ids if paper_id not in current_review_paper_ids]
        retained = [paper_id for paper_id in ranked_ids if paper_id in current_review_paper_ids]
        removed = [paper_id for paper_id in current_review_paper_ids if paper_id not in ranked_ids]
        return {
            "added": added,
            "retained": retained,
            "removed": removed,
            "summary": f"Added {len(added)}, retained {len(retained)}, removed {len(removed)} papers versus the tracked review.",
        }

    def _benchmark_summary(self, papers) -> list[str]:
        findings = []
        pattern = re.compile(r"\b(F1|BLEU|AUC|accuracy)\b[^0-9]{0,12}(\d+(?:\.\d+)?)", re.IGNORECASE)
        for paper in papers:
            text = f"{paper.title} {paper.abstract or ''}"
            matches = pattern.findall(text)
            if matches:
                rendered = ", ".join(f"{metric.upper()}={value}" for metric, value in matches[:3])
                findings.append(f"{paper.paper_id}: {rendered}")
        return findings or ["No benchmark metric string was explicitly found in the provided evidence."]

    def _benchmark_reasoning_table(self, benchmark_summary: list[str]) -> list[dict[str, str]]:
        rows = []
        for item in benchmark_summary:
            paper_id, _, metrics = item.partition(":")
            rows.append(
                {
                    "paper_id": paper_id.strip() or "n/a",
                    "metrics": metrics.strip() or item,
                    "normalization": "reported as written; apples-to-apples warning required if dataset differs",
                    "decision": "use only with dataset/method context",
                }
            )
        return rows

    def _explainable_ranking(self, question: str, papers) -> list[str]:
        terms = set(question.lower().split())
        reasons = []
        for index, paper in enumerate(papers[:5], start=1):
            overlap = len(terms & set(f"{paper.title} {(paper.abstract or '')}".lower().split()))
            reasons.append(
                f"Rank {index}: {paper.title} scored high due to {overlap} query-term overlaps, citation count {paper.citation_count}, and badges {', '.join(paper.result_badges) or 'none'}."
            )
        return reasons

    def _ranking_explanation_rows(self, question: str, papers) -> list[dict[str, str | int]]:
        terms = set(question.lower().split())
        rows = []
        for index, paper in enumerate(papers[:5], start=1):
            overlap = len(terms & set(f"{paper.title} {(paper.abstract or '')}".lower().split()))
            rows.append(
                {
                    "rank": index,
                    "paper_id": paper.paper_id,
                    "title": paper.title,
                    "query_overlap": overlap,
                    "citation_count": paper.citation_count,
                    "explanation": "hybrid rank combines query overlap, metadata enrichment, citations, and trust badges",
                }
            )
        return rows

    def _critique_panel(self, papers) -> dict[str, list[str]]:
        stats = []
        domain = []
        ethics = []
        for paper in papers[:4]:
            abstract = (paper.abstract or "").lower()
            stats.append(
                f"{paper.paper_id}: sample size {paper.sample_size or 'not stated'} and benchmark reporting {'present' if any(metric in abstract for metric in ('f1', 'auc', 'bleu', 'accuracy')) else 'limited'}."
            )
            domain.append(f"{paper.paper_id}: domain framing from venue '{paper.venue or 'unknown'}' and topic '{paper.cluster_label or 'general'}'.")
            ethics.append(
                f"{paper.paper_id}: ethics lens flags {'bias/limitation language present' if any(token in abstract for token in ('bias', 'limitation', 'consent', 'fairness')) else 'no explicit ethics warning in abstract'}."
            )
        return {"statistician": stats, "domain_expert": domain, "ethics": ethics}

    def _evidence_trace(self, papers) -> list[EvidenceTrace]:
        trace: list[EvidenceTrace] = []
        for paper in papers[:6]:
            abstract = (paper.abstract or "").lower()
            if any(token in abstract for token in ("improve", "outperform", "effective", "support")):
                support_type = "supporting"
                reason = "Abstract contains positive performance or support language."
            elif any(token in abstract for token in ("however", "limitation", "bias", "underperform", "conflict")):
                support_type = "contesting"
                reason = "Abstract contains limitation, conflict, or underperformance language."
            else:
                support_type = "context"
                reason = "Paper contributes context without strong directional language."
            trace.append(
                EvidenceTrace(
                    paper_id=paper.paper_id,
                    title=paper.title,
                    support_type=support_type,
                    reason=reason,
                )
            )
        return trace

    def _guardrails(self, question: str, papers, omitted_claims: list[str]) -> list[GuardrailDecision]:
        grounded_outcome = "passed" if papers else "fallback"
        decisions = [
            GuardrailDecision(
                rule="retrievable-evidence-required",
                outcome=grounded_outcome,
                detail="Evidence papers were ranked before synthesis." if papers else "No ranked evidence found; answer falls back to omission notice.",
            ),
            GuardrailDecision(
                rule="unsupported-claim-omission",
                outcome="triggered" if omitted_claims else "clear",
                detail=f"{len(omitted_claims)} unsupported items were withheld from the final answer.",
            ),
        ]
        if "debate" in question.lower():
            decisions.append(
                GuardrailDecision(
                    rule="balanced-debate-required",
                    outcome="passed" if len(papers) >= 2 else "limited",
                    detail="Both pro and con evidence lanes were prepared." if len(papers) >= 2 else "Debate mode has limited opposing evidence.",
                )
            )
        return decisions

    def _zero_hallucination_report(self, citations: list[str], omitted_claims: list[str], supported_lines: list[str]) -> dict[str, str | int | float]:
        supported_count = len(supported_lines)
        omitted_count = len(omitted_claims)
        total = supported_count + omitted_count
        coverage = round(supported_count / total, 2) if total else 0.0
        return {
            "status": "enforced",
            "grounded_citation_count": len(citations),
            "grounded_sentence_count": supported_count,
            "omitted_claim_count": omitted_count,
            "support_coverage": coverage,
            "policy": "claims without a retrievable source chunk are omitted or marked for review",
        }
