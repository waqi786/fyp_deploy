import re

from app.schemas.trust import (
    BiasTagDetail,
    CitationContextLabel,
    ContradictionDetail,
    EvidenceMeterEntry,
    JournalImpactProfile,
    ModerationQueueEntry,
    SampleSizeProfile,
    StatisticalSanityCheck,
    TrustAnalysisRequest,
    TrustAnalysisResponse,
    TrustChangeLogEntry,
    TrustChecklistItem,
    TrustSignal,
)


class TrustAnalysisService:
    def analyze(self, payload: TrustAnalysisRequest) -> TrustAnalysisResponse:
        paper = payload.paper
        text = f"{paper.title}. {paper.abstract or ''}. {payload.full_text or ''}".lower()

        base_trust = 5.0
        base_novelty = 5.0
        trust_score = base_trust
        novelty_score = base_novelty
        red_flags: list[str] = []
        green_flags: list[str] = []
        signals: list[TrustSignal] = []
        changelog: list[TrustChangeLogEntry] = []

        if paper.citation_count >= 100:
            trust_score += 1.2
            evidence = f"Citation count = {paper.citation_count}"
            signals.append(TrustSignal(label="Citation traction", value=str(paper.citation_count), impact="positive", evidence=evidence, score_delta=1.2))
            green_flags.append("Strong citation traction")
            changelog.append(TrustChangeLogEntry(event="citation_traction", score_delta=1.2, reason="High citation count", evidence=evidence))
        elif paper.citation_count == 0:
            trust_score -= 0.8
            red_flags.append("No citation traction yet")
            changelog.append(TrustChangeLogEntry(event="citation_traction", score_delta=-0.8, reason="No citations", evidence="Citation count = 0"))

        if paper.is_open_access:
            trust_score += 0.5
            green_flags.append("Open access improves inspectability")
            changelog.append(TrustChangeLogEntry(event="open_access", score_delta=0.5, reason="Inspectability improved", evidence="Paper marked open access"))
        else:
            red_flags.append("Closed access limits transparency")

        if paper.year and paper.year >= 2024:
            novelty_score += 1.3
            signals.append(TrustSignal(label="Recency", value=str(paper.year), impact="positive", evidence=f"Publication year = {paper.year}", score_delta=1.3))

        sample_match = re.search(r"\b(n\s*=\s*(\d+)|(\d+)\s+(participants|samples|patients|subjects))\b", text)
        if sample_match:
            sample_size = int(next(group for group in sample_match.groups() if group and group.isdigit()))
            evidence = sample_match.group(0)
            signals.append(TrustSignal(label="Sample size", value=str(sample_size), impact="mixed", evidence=evidence))
            if sample_size < 30:
                trust_score -= 1.0
                red_flags.append("Small sample size signal")
                changelog.append(TrustChangeLogEntry(event="sample_size", score_delta=-1.0, reason="Small sample", evidence=evidence))
            elif sample_size >= 100:
                trust_score += 0.7
                green_flags.append("Healthy sample size signal")
                changelog.append(TrustChangeLogEntry(event="sample_size", score_delta=0.7, reason="Healthy sample", evidence=evidence))
        else:
            sample_size = 0
            red_flags.append("Sample size not clearly stated")

        if any(token in text for token in ("p < 0.05", "confidence interval", "cross-validation", "ablation")):
            trust_score += 0.6
            green_flags.append("Method reporting includes validation/statistical detail")
            stats_evidence = self._stats_evidence(text)
            changelog.append(TrustChangeLogEntry(event="stats_detail", score_delta=0.6, reason="Validation/statistics reported", evidence=stats_evidence))
            signals.append(TrustSignal(label="Statistical detail", value="reported", impact="positive", evidence=stats_evidence, score_delta=0.6))
        else:
            red_flags.append("Statistical detail is limited")

        if any(token in text for token in ("limitation", "future work", "error analysis")):
            trust_score += 0.4
            green_flags.append("Paper acknowledges limitations")
            changelog.append(TrustChangeLogEntry(event="limitations_acknowledged", score_delta=0.4, reason="Transparent limitations discussed", evidence=self._limitation_evidence(text)))

        if any(token in text for token in ("novel", "first", "we introduce", "new benchmark")):
            novelty_score += 0.9
            green_flags.append("Novelty language present")
            signals.append(TrustSignal(label="Novelty language", value="present", impact="positive", evidence=self._novelty_evidence(text), score_delta=0.9))

        if any(token in text for token in ("funded by", "sponsored by", "conflict of interest")):
            signals.append(TrustSignal(label="Funding/COI disclosure", value="present", impact="informational", evidence=self._funding_evidence(text)))
        else:
            red_flags.append("Funding or COI disclosure not obvious")

        overclaiming = any(token in text for token in ("state-of-the-art", "always", "guarantee", "proves that"))
        p_hacking = any(token in text for token in ("multiple comparisons", "selective reporting", "post-hoc"))
        if overclaiming:
            red_flags.append("Potential overclaiming language")
        if p_hacking:
            red_flags.append("Potential p-hacking indicator")

        peer_review_status = "peer_reviewed" if payload.peer_reviewed else "unknown"
        if payload.peer_reviewed:
            trust_score += 0.3
            green_flags.append("Peer-review status supplied as positive")
            changelog.append(TrustChangeLogEntry(event="peer_review", score_delta=0.3, reason="Peer reviewed input", evidence="peer_reviewed=True"))

        retraction_check = "retracted_or_withdrawn" if paper.is_retracted or any(token in text for token in ("retracted", "withdrawn")) else "no_retraction_signal"
        erratum_check = "erratum_or_correction_mentioned" if any(token in text for token in ("erratum", "corrigendum", "correction notice")) else "no_erratum_signal"
        conflict_of_interest_flag = "declared" if "conflict of interest" in text else "not_obvious"
        funding_transparency_flag = "disclosed" if any(token in text for token in ("funded by", "sponsored by", "grant")) else "not_obvious"
        author_track_record_summary = self._author_track_record_summary(paper, payload.related_papers)
        self_citation_ratio = self._estimate_self_citation_ratio(paper, payload.related_papers)
        self_citation_flag = self._self_citation_flag(self_citation_ratio)
        sample_size_adequacy = self._sample_size_adequacy(sample_size)
        sample_size_profile = SampleSizeProfile(
            extracted_n=sample_size,
            adequacy=sample_size_adequacy,
            explanation=self._sample_size_explanation(sample_size),
        )
        effect_size = self._extract_effect_size(text)
        reproducibility_score = self._reproducibility_score(text, paper.is_open_access)
        replication_outlook, contradictions, contradiction_details = self._replication_and_contradictions(paper, payload.related_papers)
        statistical_appropriateness = self._statistical_appropriateness(text)
        bias_tags = self._bias_tags(text)
        bias_tag_details = self._bias_tag_details(bias_tags)
        outlier_anomaly_flags = self._outlier_anomaly_flags(paper, text, sample_size)
        ci_pvalue_sanity = self._ci_pvalue_sanity(text)
        statistical_sanity_checks = self._statistical_sanity_checks(text, sample_size)
        checklist = self._methodology_checklist(text, sample_size, paper.is_open_access)
        evidence_strength_breakdown = self._evidence_breakdown(trust_score, novelty_score, reproducibility_score, paper.citation_count)
        evidence_meter = self._evidence_meter(evidence_strength_breakdown)
        citation_context_labels = self._label_citation_contexts(payload.citation_contexts)
        moderation_status = "flagged" if len(red_flags) >= 3 or overclaiming or p_hacking else "clean"
        moderation_queue_entry = self._moderation_queue_entry(
            payload=payload,
            red_flags=red_flags,
            contradiction_details=contradiction_details,
            outlier_anomaly_flags=outlier_anomaly_flags,
        )
        if moderation_queue_entry and moderation_status == "clean":
            moderation_status = moderation_queue_entry.status

        evidence_strength = "high" if trust_score >= 7.5 else "medium" if trust_score >= 5.5 else "low"
        confidence_score = min(0.95, 0.45 + len(signals) * 0.08)

        return TrustAnalysisResponse(
            trust_score=round(max(1.0, min(10.0, trust_score)), 2),
            novelty_score=round(max(1.0, min(10.0, novelty_score)), 2),
            evidence_strength=evidence_strength,
            confidence_score=round(confidence_score, 2),
            peer_review_status=peer_review_status,
            journal_quartile=paper.journal_quartile,
            journal_impact_profile=self._journal_impact_profile(paper),
            retraction_check=retraction_check,
            erratum_check=erratum_check,
            conflict_of_interest_flag=conflict_of_interest_flag,
            funding_transparency_flag=funding_transparency_flag,
            author_track_record_summary=author_track_record_summary,
            self_citation_ratio=self_citation_ratio,
            self_citation_flag=self_citation_flag,
            sample_size_adequacy=sample_size_adequacy,
            sample_size_profile=sample_size_profile,
            effect_size=effect_size,
            reproducibility_score=reproducibility_score,
            replication_outlook=replication_outlook,
            statistical_appropriateness=statistical_appropriateness,
            contradiction_summary=contradictions,
            contradiction_details=contradiction_details,
            bias_tags=bias_tags,
            bias_tag_details=bias_tag_details,
            outlier_anomaly_flags=outlier_anomaly_flags,
            ci_pvalue_sanity=ci_pvalue_sanity,
            statistical_sanity_checks=statistical_sanity_checks,
            methodology_quality_checklist=checklist,
            evidence_strength_breakdown=evidence_strength_breakdown,
            evidence_meter=evidence_meter,
            score_trace={
                "base_trust": base_trust,
                "base_novelty": base_novelty,
                "final_trust": round(max(1.0, min(10.0, trust_score)), 2),
                "final_novelty": round(max(1.0, min(10.0, novelty_score)), 2),
            },
            citation_context_labels=citation_context_labels,
            moderation_status=moderation_status,
            moderation_queue_entry=moderation_queue_entry,
            trust_score_changelog=changelog,
            red_flags=red_flags,
            green_flags=green_flags,
            signals=signals,
        )

    def _estimate_self_citation_ratio(self, paper, related_papers) -> float:
        if not paper.authors or not related_papers:
            return 0.0
        primary_authors = {author.get("name", "").lower() for author in paper.authors}
        if not primary_authors:
            return 0.0
        overlaps = 0
        for related in related_papers:
            related_authors = {author.get("name", "").lower() for author in related.authors}
            if primary_authors & related_authors:
                overlaps += 1
        return round(overlaps / max(len(related_papers), 1), 2)

    def _sample_size_adequacy(self, sample_size: int) -> str:
        if sample_size >= 200:
            return "strong"
        if sample_size >= 60:
            return "adequate"
        if sample_size > 0:
            return "limited"
        return "unclear"

    def _sample_size_explanation(self, sample_size: int) -> str:
        if sample_size >= 200:
            return "Sample size is strong enough for most benchmark-style comparisons."
        if sample_size >= 60:
            return "Sample size is reasonable but still worth checking against task complexity."
        if sample_size > 0:
            return "Sample size may be too small for broad generalization claims."
        return "The paper does not state sample size clearly enough for confidence."

    def _extract_effect_size(self, text: str) -> str:
        match = re.search(r"\b(cohen'?s d|odds ratio|hazard ratio|effect size)\b[^.]{0,30}", text)
        return match.group(0).strip() if match else "Not explicitly reported"

    def _reproducibility_score(self, text: str, is_open_access: bool) -> float:
        score = 4.0
        if is_open_access:
            score += 1.0
        if any(token in text for token in ("github", "code available", "repository")):
            score += 2.0
        if any(token in text for token in ("dataset", "benchmark")):
            score += 1.0
        if any(token in text for token in ("hyperparameter", "ablation")):
            score += 1.0
        return round(min(10.0, score), 2)

    def _replication_and_contradictions(self, paper, related_papers) -> tuple[str, list[str], list[ContradictionDetail]]:
        contradictions = []
        details: list[ContradictionDetail] = []
        positive = " ".join(filter(None, [paper.abstract])).lower()
        for related in related_papers:
            abstract = (related.abstract or "").lower()
            if ("outperform" in positive or "improve" in positive) and ("limitation" in abstract or "underperform" in abstract):
                summary = f"{paper.title} may conflict with {related.title} on outcome framing."
                contradictions.append(summary)
                details.append(
                    ContradictionDetail(
                        summary=summary,
                        focal_paper_id=paper.paper_id,
                        related_paper_id=related.paper_id,
                        supporting_evidence=[
                            (paper.abstract or "")[:220],
                            (related.abstract or "")[:220],
                        ],
                    )
                )
        if contradictions:
            return "mixed", contradictions, details
        return ("promising" if related_papers else "unknown"), [], []

    def _statistical_appropriateness(self, text: str) -> str:
        if any(token in text for token in ("randomized", "confidence interval", "cross-validation", "ablation")):
            return "appropriate"
        if any(token in text for token in ("correlation only", "exploratory")):
            return "needs caution"
        return "unclear"

    def _bias_tags(self, text: str) -> list[str]:
        tags = []
        if "single-center" in text or "single centre" in text:
            tags.append("Single-center bias")
        if "public dataset" in text and "real-world" not in text:
            tags.append("Dataset-shift risk")
        if "english-only" in text or "english only" in text:
            tags.append("Language bias")
        return tags or ["No major bias tag detected"]

    def _bias_tag_details(self, tags: list[str]) -> list[BiasTagDetail]:
        explanations = {
            "Single-center bias": "Findings may depend too heavily on one site, lab, or cohort.",
            "Dataset-shift risk": "Performance on curated public data may not transfer to noisier real-world settings.",
            "Language bias": "English-only evidence may fail to generalize to multilingual deployment.",
            "No major bias tag detected": "No strong bias pattern was surfaced by the current heuristic scan.",
        }
        return [BiasTagDetail(label=tag, explanation=explanations.get(tag, "Bias signal detected.")) for tag in tags]

    def _ci_pvalue_sanity(self, text: str) -> list[str]:
        checks = []
        if "p < 0.05" in text:
            checks.append("P-value threshold reported")
        if "confidence interval" in text:
            checks.append("Confidence interval reported")
        if not checks:
            checks.append("No CI/p-value sanity signal detected")
        return checks

    def _statistical_sanity_checks(self, text: str, sample_size: int) -> list[StatisticalSanityCheck]:
        checks = []
        checks.append(
            StatisticalSanityCheck(
                label="P-value reporting",
                status="present" if "p < 0.05" in text or "p-value" in text else "missing",
                evidence="p < 0.05" if "p < 0.05" in text else ("p-value" if "p-value" in text else None),
            )
        )
        checks.append(
            StatisticalSanityCheck(
                label="Confidence interval reporting",
                status="present" if "confidence interval" in text else "missing",
                evidence="confidence interval" if "confidence interval" in text else None,
            )
        )
        checks.append(
            StatisticalSanityCheck(
                label="Sample size plausibility",
                status="caution" if 0 < sample_size < 30 else ("good" if sample_size >= 30 else "unclear"),
                evidence=f"n={sample_size}" if sample_size else None,
            )
        )
        return checks

    def _outlier_anomaly_flags(self, paper, text: str, sample_size: int) -> list[str]:
        flags = []
        if sample_size and sample_size < 20 and paper.citation_count >= 100:
            flags.append("High-impact claim is supported by a very small sample")
        if "100%" in text or "perfect accuracy" in text:
            flags.append("Reported performance looks unusually perfect")
        if paper.year and paper.year >= 2024 and "state-of-the-art" in text and sample_size < 30:
            flags.append("Strong SOTA claim with limited sample support")
        return flags

    def _author_track_record_summary(self, paper, related_papers) -> str:
        if not paper.authors:
            return "Author track record unavailable"
        primary_authors = [author.get("name", "").strip() for author in paper.authors if author.get("name")]
        if not primary_authors:
            return "Author track record unavailable"
        overlap = 0
        for related in related_papers:
            related_names = {author.get("name", "").strip().lower() for author in related.authors if author.get("name")}
            if any(name.lower() in related_names for name in primary_authors):
                overlap += 1
        if overlap >= 3:
            return "Authors show a strong repeated presence across related papers in this slice."
        if overlap >= 1:
            return "Authors appear in nearby related work, suggesting an established track record in this topic."
        return "Authors do not appear repeatedly in the supplied related-paper slice."

    def _moderation_queue_entry(
        self,
        *,
        payload: TrustAnalysisRequest,
        red_flags: list[str],
        contradiction_details: list[ContradictionDetail],
        outlier_anomaly_flags: list[str],
    ) -> ModerationQueueEntry | None:
        evidence = red_flags[:2] + outlier_anomaly_flags[:2]
        if contradiction_details:
            evidence.append(contradiction_details[0].summary)
        if payload.manual_flag_as_questionable:
            return ModerationQueueEntry(
                status="queued_for_review",
                reason="Manually flagged as questionable",
                note=payload.moderation_note,
                evidence=evidence,
            )
        if len(red_flags) >= 3 or outlier_anomaly_flags:
            return ModerationQueueEntry(
                status="flagged",
                reason="Automatic moderation due to multiple red flags or anomaly signals",
                note=payload.moderation_note,
                evidence=evidence,
            )
        return None

    def _methodology_checklist(self, text: str, sample_size: int, is_open_access: bool) -> list[TrustChecklistItem]:
        return [
            TrustChecklistItem(label="Sample size stated", passed=sample_size > 0, explanation="Explicit sample size improves auditability."),
            TrustChecklistItem(label="Baseline comparison", passed="baseline" in text or "outperform" in text, explanation="Comparative baselines help judge effect realism."),
            TrustChecklistItem(label="Error or limitation analysis", passed="limitation" in text or "error analysis" in text, explanation="Transparent limits reduce overclaiming."),
            TrustChecklistItem(label="Open access or inspectable artifact", passed=is_open_access or "github" in text, explanation="Public access improves reproducibility."),
        ]

    def _evidence_breakdown(self, trust_score: float, novelty_score: float, reproducibility_score: float, citations: int) -> dict[str, float]:
        return {
            "method_rigor": round(min(10.0, trust_score), 2),
            "novelty": round(min(10.0, novelty_score), 2),
            "reproducibility": round(reproducibility_score, 2),
            "citation_support": round(min(10.0, citations / 20), 2),
        }

    def _evidence_meter(self, evidence_strength_breakdown: dict[str, float]) -> list[EvidenceMeterEntry]:
        explanations = {
            "method_rigor": "How well the paper reports validation, limitations, and methodological detail.",
            "novelty": "How strongly the paper appears to add something new relative to nearby work.",
            "reproducibility": "How inspectable and repeatable the setup looks from text and metadata.",
            "citation_support": "How much follow-on literature attention the work has attracted so far.",
        }
        return [
            EvidenceMeterEntry(label=label, score=score, explanation=explanations.get(label, "Evidence slice."))
            for label, score in evidence_strength_breakdown.items()
        ]

    def _label_citation_contexts(self, contexts: list[str]) -> list[CitationContextLabel]:
        labeled = []
        for context in contexts:
            lowered = context.lower()
            if any(token in lowered for token in ("support", "consistent with", "agrees with")):
                label = "support"
            elif any(token in lowered for token in ("however", "contrary", "unlike", "dispute")):
                label = "dispute"
            else:
                label = "mention"
            labeled.append(CitationContextLabel(context=context, label=label))
        return labeled

    def _stats_evidence(self, text: str) -> str:
        for token in ("p < 0.05", "confidence interval", "cross-validation", "ablation"):
            if token in text:
                return token
        return "statistical detail detected"

    def _limitation_evidence(self, text: str) -> str:
        for token in ("limitation", "future work", "error analysis"):
            if token in text:
                return token
        return "limitations discussed"

    def _novelty_evidence(self, text: str) -> str:
        for token in ("novel", "first", "we introduce", "new benchmark"):
            if token in text:
                return token
        return "novelty language detected"

    def _funding_evidence(self, text: str) -> str:
        for token in ("funded by", "sponsored by", "conflict of interest"):
            if token in text:
                return token
        return "disclosure mentioned"

    def _journal_impact_profile(self, paper) -> JournalImpactProfile:
        quartile = paper.journal_quartile
        if quartile == "q1":
            tier = "high"
        elif quartile == "q2":
            tier = "strong"
        elif quartile in {"q3", "q4"}:
            tier = "emerging"
        else:
            tier = "unknown"
        if paper.citation_count >= 100:
            citation_signal = "strong citation support"
        elif paper.citation_count >= 25:
            citation_signal = "moderate citation support"
        else:
            citation_signal = "early or limited citation support"
        return JournalImpactProfile(quartile=quartile, impact_tier=tier, citation_signal=citation_signal)

    def _self_citation_flag(self, ratio: float) -> str:
        if ratio >= 0.5:
            return "high"
        if ratio >= 0.2:
            return "moderate"
        return "low"
