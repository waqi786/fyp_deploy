from datetime import UTC, datetime

from app.schemas.document import ExtractedFigure
from app.schemas.draft import DraftGenerationResponse
from app.services.models.providers import get_default_model_provider
from app.services.writing.self_critique import SelfCritiqueService


URDU_SECTION_LABELS = {
    "abstract": "خلاصہ",
    "introduction": "تعارف",
    "methodology": "طریقہ کار",
    "results": "نتائج",
    "discussion": "بحث",
    "conclusion": "نتیجہ",
}


class DraftGenerationService:
    def __init__(self) -> None:
        self.provider = get_default_model_provider()
        self.critic = SelfCritiqueService()

    def generate(self, title: str, extracted_text: str, figures: list[ExtractedFigure], target_style: str, language: str) -> DraftGenerationResponse:
        structured = self.provider.structured_sections(title, extracted_text)
        figure_analyses = [self.provider.analyze_figure(figure.caption) for figure in figures]
        source_spans = [extracted_text[:280]] + [figure.caption for figure in figures[:2]]
        sections = {
            "abstract": structured["problem"],
            "introduction": structured["problem"],
            "methodology": structured["methodology"],
            "results": structured["findings"],
            "discussion": " ".join(
                [structured["findings"]] + [analysis["description"] for analysis in figure_analyses]
            ).strip(),
            "conclusion": structured["conclusion"] or structured["findings"],
        }
        critique = self.critic.critique(" ".join(value for value in sections.values() if value), [extracted_text[:500]])
        if language.lower() == "ur":
            sections = {key: self._urdu_academic_section(key, value) for key, value in sections.items()}
        if target_style.lower() == "ieee":
            sections["introduction"] = f"In IEEE style, {sections['introduction']}"
        return DraftGenerationResponse(
            sections=sections,
            self_critique=critique,
            figure_analysis_count=len(figure_analyses),
            confidence_score=round(min(0.95, 0.62 + len(figure_analyses) * 0.05), 2),
            source_spans=source_spans,
            model_used=self.provider.provider_name,
            generated_at=datetime.now(UTC).isoformat(),
        )

    def _urdu_academic_section(self, section_key: str, content: str) -> str:
        label = URDU_SECTION_LABELS.get(section_key, section_key)
        return (
            f"{label}: یہ حصہ اصل مقالے کے ماخذ متن اور فراہم کردہ شواہد کی بنیاد پر تیار کیا گیا ہے۔ "
            f"اہم نکتہ: {content} "
            "حتمی جمع کروانے سے پہلے حوالہ جات اور تکنیکی اصطلاحات کی انسانی جانچ ضروری ہے۔"
        )
