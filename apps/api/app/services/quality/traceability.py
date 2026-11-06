import re

from app.schemas.quality import (
    TraceabilityCheckRequest,
    TraceabilityCheckResponse,
    TraceableSentence,
)


class TraceabilityGuardService:
    def validate(self, payload: TraceabilityCheckRequest) -> TraceabilityCheckResponse:
        evidence = payload.source_spans + payload.retrieved_chunks
        units = self._split_units(payload.answer)
        traceable: list[TraceableSentence] = []
        unsupported: list[str] = []
        supported_count = 0

        for unit in units:
            inference = unit.lower().startswith("ai inference, not from source:")
            source_span = self._best_support(unit, evidence)
            supported = bool(source_span) or inference
            if source_span:
                supported_count += 1
            elif not inference:
                unsupported.append(unit)
            traceable.append(
                TraceableSentence(
                    sentence=unit,
                    supported=supported,
                    inference_only=inference,
                    source_span=source_span,
                )
            )

        denominator = max(1, len([item for item in traceable if not item.inference_only]))
        coverage = round(supported_count / denominator, 3)
        passed = len(unsupported) == 0
        return TraceabilityCheckResponse(
            passed=passed,
            coverage=coverage,
            traceable_sentences=traceable,
            unsupported_sentences=unsupported,
        )

    def _split_units(self, answer: str) -> list[str]:
        raw = [segment.strip() for segment in re.split(r"\n+|(?<=[.!?])\s+", answer) if segment.strip()]
        return raw

    def _best_support(self, sentence: str, evidence: list[str]) -> str | None:
        sentence_tokens = self._tokens(sentence)
        best = (0.0, None)
        for item in evidence:
            evidence_tokens = self._tokens(item)
            union = sentence_tokens | evidence_tokens
            if not union:
                continue
            overlap = len(sentence_tokens & evidence_tokens) / len(union)
            if overlap > best[0]:
                best = (overlap, item)
        return best[1] if best[0] >= 0.18 else None

    def _tokens(self, text: str) -> set[str]:
        return set(re.findall(r"\b[a-zA-Z][a-zA-Z0-9-]+\b", text.lower()))

