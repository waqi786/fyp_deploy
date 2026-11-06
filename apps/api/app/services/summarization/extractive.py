import re
from collections import Counter
from datetime import UTC, datetime

from app.schemas.summary import GlossaryEntry, GlossaryHoverSpan, OutlineSectionDetail, SummaryResponse, SummaryTier
from app.services.summarization.academic import (
    acronym_expansions,
    auto_outline,
    explain_paragraph,
    estimate_reading_time,
    exam_qa,
    extract_contributions_and_limitations,
    extract_datasets,
    extract_glossary,
    freshness_indicator,
    funding_and_coi,
    infer_difficulty,
    key_figure_caption,
    localize_academic_text,
    localize_list,
    methodology_and_results_boxes,
    narration_script,
    related_work_summary,
    reproducibility_checklist,
    statistical_flags,
    study_limitation_severity,
    translate_summary_payload,
)
from app.services.models.providers import get_default_model_provider


STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are", "was", "were",
    "this", "that", "it", "as", "by", "from", "be", "at", "we", "our",
}


def _sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text.strip()) if sentence.strip()]


def _keywords(text: str) -> Counter[str]:
    tokens = re.findall(r"\b[a-zA-Z][a-zA-Z-]+\b", text.lower())
    return Counter(token for token in tokens if token not in STOPWORDS)


def _compact(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rsplit(' ', 1)[0]}..."


def _title_content_alignment(title: str, content: str) -> float:
    title_terms = {token for token in re.findall(r"\b[a-zA-Z][a-zA-Z-]{3,}\b", title.lower()) if token not in STOPWORDS}
    if not title_terms:
        return 1.0
    content_terms = set(re.findall(r"\b[a-zA-Z][a-zA-Z-]{3,}\b", content.lower()))
    return len(title_terms & content_terms) / len(title_terms)


class ExtractiveSummarizer:
    def __init__(self, provider=None) -> None:
        self.provider = provider or get_default_model_provider()

    def summarize(
        self,
        title: str,
        content: str,
        language: str = "en",
        audience: str = "expert",
        summary_length: str = "medium",
        target_languages: list[str] | None = None,
    ) -> SummaryResponse:
        sentences = _sentences(content)
        keywords = _keywords(content)
        ranked = []
        for index, sentence in enumerate(sentences):
            words = re.findall(r"\b[a-zA-Z][a-zA-Z-]+\b", sentence.lower())
            score = sum(keywords[word] for word in words)
            if index < 3:
                score += 6 - index
            ranked.append((score, sentence))
        length_mode = summary_length.lower()
        audience_mode = audience.lower()
        depth_limit = {"short": 2, "medium": 5, "long": 9}.get(length_mode, 5)
        bullet_limit = {"short": 2, "medium": 4, "long": 7}.get(length_mode, 4)
        deep_limit = {"short": 2, "medium": 5, "long": 9}.get(length_mode, 5)
        top = [sentence for _, sentence in sorted(ranked, key=lambda item: item[0], reverse=True)[:depth_limit]]
        alignment = _title_content_alignment(title, content)
        title_mismatch = bool(title.strip() and content.strip() and alignment < 0.25)
        tldr = top[0] if top else title
        fallback_used = False
        try:
            structured = self.provider.structured_sections(title, content)
        except Exception:
            fallback_used = True
            structured = self._fallback_structured_sections(title, sentences)
        if not all(structured.values()):
            fallback_used = True
            structured = self._fallback_structured_sections(title, sentences)
        bullet_summary = top[:bullet_limit]
        if length_mode == "short":
            tldr = _compact(tldr, 180)
            bullet_summary = [_compact(point, 150) for point in bullet_summary]
        elif length_mode == "long":
            extra_context = [
                sentence for sentence in sentences
                if sentence not in bullet_summary and any(token in sentence.lower() for token in ("dataset", "sample", "limitation", "future", "code", "baseline", "figure", "table"))
            ]
            bullet_summary = (bullet_summary + extra_context)[:bullet_limit]
        deep_dive = " ".join(top[:deep_limit])
        equations = re.findall(r"(?:[A-Za-z]\s*=\s*[^.\n]{3,40})", content)[:10]
        glossary = extract_glossary(content)
        glossary_entries = [
            GlossaryEntry(
                term=term,
                definition=definition,
                source_span=f"glossary:{index + 1}:{term}",
            )
            for index, (term, definition) in enumerate(glossary.items())
        ]
        hover_glossary_spans = self._hover_glossary_spans(content, glossary)
        difficulty_score, prerequisites = infer_difficulty(content)
        contributions, limitations = extract_contributions_and_limitations(content)
        datasets = extract_datasets(content)
        methodology_box, results_box = methodology_and_results_boxes(content)
        reproducibility = reproducibility_checklist(content)
        funding = funding_and_coi(content)
        related_work = related_work_summary(content)
        outline = auto_outline(title)
        outline_sections = [
            OutlineSectionDetail(label=label, source_span=f"outline:{index + 1}:{label}")
            for index, label in enumerate(outline)
        ]
        reading_time = estimate_reading_time(content)
        key_figure = key_figure_caption(content)
        acronyms = acronym_expansions(content)
        stats = statistical_flags(content)
        qa = exam_qa(title, content)
        limitation_severity = study_limitation_severity(content, limitations)
        if audience_mode == "beginner":
            beginner_labels = ["Main idea", "How it works", "What it found", "Important caution", "Why it matters", "What to check next", "Takeaway"]
            bullet_summary = [
                f"{beginner_labels[index] if index < len(beginner_labels) else 'Point'}: {_compact(point, 170)}"
                for index, point in enumerate(bullet_summary)
            ]
            structured = {
                "problem": f"In simple words: {_compact(structured.get('problem', tldr), 420)}",
                "methodology": f"How they did it: {_compact(structured.get('methodology', methodology_box), 420)}",
                "findings": f"What they found: {_compact(structured.get('findings', results_box), 420)}",
                "conclusion": f"What to remember: {_compact(structured.get('conclusion', tldr), 420)}",
            }
            methodology_box = f"Simple explanation: {_compact(methodology_box, 520)}"
            results_box = f"Simple explanation: {_compact(results_box, 520)}"
            deep_dive = " ".join([structured["problem"], structured["methodology"], structured["findings"], structured["conclusion"]])
        else:
            structured = {
                "problem": _compact(structured.get("problem", tldr), 520),
                "methodology": _compact(structured.get("methodology", methodology_box), 560),
                "findings": _compact(structured.get("findings", results_box), 560),
                "conclusion": _compact(structured.get("conclusion", tldr), 520),
            }
            if length_mode == "long":
                deep_dive = " ".join(
                    [
                        f"Problem: {structured['problem']}",
                        f"Methodology: {structured['methodology']}",
                        f"Findings: {structured['findings']}",
                        f"Limitations: {' '.join(limitations[:2])}",
                    ]
                )
        audience_guidance = (
            "Explains terms plainly and foregrounds prerequisites for first-time readers."
            if audience.lower() == "beginner"
            else "Keeps technical language intact and assumes domain familiarity."
        )
        translations = translate_summary_payload(
            tldr=tldr,
            structured_summary=structured,
            contributions=contributions,
            target_languages=target_languages or ["ur", "es", "fr", "de", "ar", "tr", "zh", "hi", "fa", "id"],
        )
        urdu_summary = {
            "problem": str(translations["ur"]["problem"]),
            "methodology": str(translations["ur"]["methodology"]),
            "findings": str(translations["ur"]["findings"]),
            "conclusion": str(translations["ur"]["conclusion"]),
        }
        response_language = language.lower()
        if response_language in translations:
            language_payload = translations[response_language]
            structured = {
                "problem": str(language_payload["problem"]),
                "methodology": str(language_payload["methodology"]),
                "findings": str(language_payload["findings"]),
                "conclusion": str(language_payload["conclusion"]),
            }
            tldr = str(language_payload["tldr"])
            bullet_summary = localize_list(bullet_summary, response_language)
            contributions = [str(item) for item in language_payload.get("contributions", contributions)]
            limitations = localize_list(limitations, response_language)
            prerequisites = localize_list(prerequisites, response_language)
            qa = [
                {
                    "question": localize_academic_text(item["question"], response_language),
                    "answer": localize_academic_text(item["answer"], response_language),
                }
                for item in qa
            ]
            methodology_box = localize_academic_text(methodology_box, response_language)
            results_box = localize_academic_text(results_box, response_language)
            related_work = localize_academic_text(related_work, response_language)
            audience_guidance = localize_academic_text(audience_guidance, response_language)
            deep_dive = localize_academic_text(deep_dive, response_language)
        confidence = self._confidence_score(
            sentences=sentences,
            content=content,
            reproducibility=reproducibility,
            stats=stats,
            alignment=alignment,
            summary_length=length_mode,
            audience=audience_mode,
        )
        if title_mismatch:
            stats = [
                "Title/content mismatch detected: the title terms do not strongly match the pasted paper text.",
                *stats,
            ]
        source_spans = self._source_spans(top[:6])
        narration = narration_script(title, tldr, bullet_summary, structured.get("conclusion", tldr))
        if response_language in translations:
            narration = {
                "plain_text": localize_academic_text(narration["plain_text"], response_language),
                "ssml": localize_academic_text(narration["ssml"], response_language),
            }
        explainability_preview = self._paragraph_explainability_preview(sentences, audience)
        if response_language in translations:
            explainability_preview = [
                {
                    **item,
                    "explanation": localize_academic_text(str(item["explanation"]), response_language),
                    "key_points": localize_list([str(point) for point in item["key_points"]], response_language),
                }
                for item in explainability_preview
            ]
        key_figure_insight = (
            f"Selected figure focus: {key_figure}. This figure is likely the fastest entry point for understanding the main experimental claim."
            if key_figure
            else None
        )
        summary_tiers = {
            "30_sec": SummaryTier(label="30-sec bullet", content=" ".join(bullet_summary[:3]), source_spans=source_spans[:3]),
            "2_min": SummaryTier(label="2-min structured", content=" ".join(structured.values()), source_spans=source_spans[:4]),
            "5_min": SummaryTier(label="5-min deep-dive", content=deep_dive, source_spans=source_spans),
        }
        return SummaryResponse(
            tldr=tldr,
            bullet_summary=bullet_summary,
            structured_summary=structured,
            deep_dive=deep_dive,
            summary_tiers=summary_tiers,
            equations=equations,
            urdu_summary=urdu_summary,
            glossary=glossary,
            glossary_entries=glossary_entries,
            hover_glossary_spans=hover_glossary_spans,
            difficulty_score=difficulty_score,
            prerequisites=prerequisites,
            contributions=contributions,
            limitations=limitations,
            methodology_box=methodology_box,
            results_box=results_box,
            datasets=datasets,
            reproducibility_checklist=reproducibility,
            funding_or_coi=funding,
            freshness_indicator=freshness_indicator(_extract_year(content)),
            related_work_summary=related_work,
            auto_outline=outline,
            outline_sections=outline_sections,
            reading_time_minutes=reading_time,
            key_figure_caption=key_figure,
            acronym_expansions=acronyms,
            statistical_flags=stats,
            study_limitation_severity_score=limitation_severity,
            exam_qa=qa,
            translations=translations,
            translation_languages=list(translations.keys()),
            audio_narration=narration,
            audience_mode=audience,
            audience_guidance=audience_guidance,
            summary_length_applied=summary_length,
            paragraph_explainability_preview=explainability_preview,
            key_figure_insight=key_figure_insight,
            confidence_score=confidence,
            model_used=self.provider.provider_name,
            source_spans=source_spans,
            generated_at=datetime.now(UTC).isoformat(),
            fallback_used=fallback_used,
        )

    def _confidence_score(
        self,
        *,
        sentences: list[str],
        content: str,
        reproducibility: dict[str, bool],
        stats: list[str],
        alignment: float,
        summary_length: str,
        audience: str,
    ) -> float:
        word_count = len(content.split())
        score = 0.45
        score += min(len(sentences), 10) * 0.025
        score += min(word_count, 1800) / 1800 * 0.12
        score += sum(1 for passed in reproducibility.values() if passed) * 0.025
        score += 0.04 if any("No explicit" not in flag for flag in stats) else 0.0
        score += 0.08 if alignment >= 0.5 else -0.12 if alignment < 0.25 else 0.0
        score += {"short": -0.03, "medium": 0.0, "long": 0.03}.get(summary_length, 0.0)
        score += 0.01 if audience == "expert" else -0.01
        return round(max(0.32, min(0.93, score)), 2)

    def explain(self, paragraph: str, audience: str = "beginner", language: str = "en") -> dict[str, object]:
        explanation, points = explain_paragraph(paragraph, audience)
        glossary = extract_glossary(paragraph, limit=5)
        language_key = language.lower()
        explanation = localize_academic_text(explanation, language_key)
        points = localize_list(points, language_key)
        language = "en"
        if language.lower() == "ur":
            explanation = f"اردو تشریح: {explanation}"
        if language.lower() == "ur":
            explanation = f"اردو تشریح: {explanation.split(': ', 1)[-1]}"
        return {
            "explanation": explanation,
            "simplified_points": points,
            "glossary_terms": glossary,
            "audience_mode": audience,
            "reading_level": "advanced" if audience.lower() == "expert" else "plain-language",
            "source_span": f"paragraph:1:{paragraph[:180]}",
            "confidence_score": 0.76 if paragraph.strip() else 0.2,
            "model_used": self.provider.provider_name,
        }

    def _fallback_structured_sections(self, title: str, sentences: list[str]) -> dict[str, str]:
        if not sentences:
            return {
                "problem": title,
                "methodology": title,
                "findings": title,
                "conclusion": title,
            }
        return {
            "problem": sentences[0],
            "methodology": sentences[1] if len(sentences) > 1 else sentences[0],
            "findings": sentences[2] if len(sentences) > 2 else sentences[0],
            "conclusion": sentences[3] if len(sentences) > 3 else sentences[-1],
        }

    def _source_spans(self, top_sentences: list[str]) -> list[str]:
        return [f"summary:{index + 1}:{sentence[:180]}" for index, sentence in enumerate(top_sentences) if sentence]

    def _paragraph_explainability_preview(self, sentences: list[str], audience: str) -> list[dict[str, str | list[str]]]:
        preview = []
        for index, sentence in enumerate(sentences[:3]):
            explanation, points = explain_paragraph(sentence, audience)
            preview.append(
                {
                    "source_span": f"paragraph:{index + 1}:{sentence[:160]}",
                    "explanation": explanation,
                    "key_points": points[:2],
                }
            )
        return preview

    def _hover_glossary_spans(self, content: str, glossary: dict[str, str]) -> list[GlossaryHoverSpan]:
        spans: list[GlossaryHoverSpan] = []
        lowered = content.lower()
        for term, definition in list(glossary.items())[:8]:
            start = lowered.find(term.lower())
            if start >= 0:
                spans.append(
                    GlossaryHoverSpan(
                        term=term,
                        definition=definition,
                        start_offset=start,
                        end_offset=start + len(term),
                    )
                )
        return spans


def _extract_year(content: str) -> int | None:
    match = re.search(r"\b(20\d{2}|19\d{2})\b", content)
    return int(match.group(1)) if match else None
