import re

STOPWORDS = {
    "this", "that", "paper", "study", "shows", "show", "also", "with", "from", "into", "than",
    "have", "has", "had", "will", "would", "could", "should", "their", "there", "every",
}


class SelfCritiqueService:
    def critique(self, draft: str, source_spans: list[str]) -> dict[str, list[str]]:
        trace = self.critique_trace(draft, source_spans)
        supported = [entry["sentence"] for entry in trace if entry["verdict"] == "supported"]
        unsupported = [entry["sentence"] for entry in trace if entry["verdict"] == "unsupported"]
        return {"supported_claims": supported, "unsupported_claims": unsupported}

    def critique_trace(self, draft: str, source_spans: list[str]) -> list[dict[str, object]]:
        supported = []
        normalized_sources = " ".join(source_spans).lower()
        for sentence in re.split(r"(?<=[.!?])\s+", draft.strip()):
            cleaned = sentence.strip()
            if not cleaned:
                continue
            terms = [
                term.lower()
                for term in re.findall(r"\b[a-zA-Z][a-zA-Z-]{3,}\b", cleaned)
                if term.lower() not in STOPWORDS
            ]
            matched_terms = [term for term in terms if term in normalized_sources]
            matches = len(matched_terms)
            ratio = matches / len(terms) if terms else 0
            verdict = "supported" if ratio >= 0.4 else "unsupported"
            supported.append(
                {
                    "sentence": cleaned,
                    "verdict": verdict,
                    "matched_terms": matched_terms,
                    "confidence_score": round(min(1.0, 0.35 + ratio), 2),
                    "source_span": source_spans[:2],
                }
            )
        return supported
