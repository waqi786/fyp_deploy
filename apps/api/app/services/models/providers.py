import re
from dataclasses import dataclass

from app.core.config import settings
from app.services.models.adapters import BaseLLMAdapter, build_llm_adapter


@dataclass
class ProviderSections:
    problem: str
    methodology: str
    findings: str
    conclusion: str


class ModelProvider:
    def __init__(self, adapter: BaseLLMAdapter | None = None) -> None:
        self.adapter = adapter or build_llm_adapter(settings.default_llm_provider)
        self.provider_name = self.adapter.provider_name

    def structured_sections(self, title: str, content: str) -> dict[str, str]:
        heuristic = self._heuristic_sections(title, content)
        prompt = (
            "Return a grounded academic summary with problem, methodology, findings, conclusion.\n"
            f"Title: {title}\n"
            f"Content: {content[:4000]}"
        )
        try:
            llm_output = self.adapter.complete(prompt)
            sections = self._sections_from_text(title, content, llm_output.text)
            if all(sections.values()):
                return sections
        except Exception:
            pass
        return heuristic

    def analyze_figure(self, caption: str) -> dict[str, str | list[str]]:
        lowered = caption.lower()
        if "table" in lowered:
            chart_type = "table"
        elif any(token in lowered for token in ("accuracy", "auc", "f1", "loss", "curve")):
            chart_type = "line_chart"
        elif any(token in lowered for token in ("distribution", "counts", "frequency", "bar")):
            chart_type = "bar_chart"
        else:
            chart_type = "figure"
        return {
            "chart_type": chart_type,
            "description": caption or "Figure detected from nearby caption text.",
            "data_insights": [f"Caption suggests a {chart_type.replace('_', ' ')} focused on the paper's main evidence."],
        }

    def _heuristic_sections(self, title: str, content: str) -> dict[str, str]:
        sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", content) if segment.strip()]
        return {
            "problem": sentences[0] if len(sentences) > 0 else title,
            "methodology": sentences[1] if len(sentences) > 1 else sentences[0] if sentences else title,
            "findings": sentences[2] if len(sentences) > 2 else sentences[0] if sentences else title,
            "conclusion": sentences[3] if len(sentences) > 3 else sentences[-1] if sentences else title,
        }

    def _sections_from_text(self, title: str, content: str, llm_text: str) -> dict[str, str]:
        sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", llm_text) if segment.strip()]
        if len(sentences) < 2:
            return self._heuristic_sections(title, content)
        heuristic = self._heuristic_sections(title, content)
        return {
            "problem": sentences[0] if sentences else heuristic["problem"],
            "methodology": sentences[1] if len(sentences) > 1 else heuristic["methodology"],
            "findings": sentences[2] if len(sentences) > 2 else heuristic["findings"],
            "conclusion": sentences[3] if len(sentences) > 3 else sentences[-1] if sentences else heuristic["conclusion"],
        }


def get_default_model_provider() -> ModelProvider:
    return ModelProvider()
