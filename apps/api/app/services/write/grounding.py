"""Grounded writing for the Write tab.

* Outline: built deterministically from the selected papers for the chosen review style (thematic, methodological,
  chronological or narrative); every section lists the source numbers it should draw on.
* Section writing: the AI router writes one section at a time from those sources only. Citations are [n] markers that
  must point to a given source. Afterwards every sentence is checked: no marker, a marker to a source that was not
  given, or a number that does not appear in the cited sources → the sentence is flagged "unsupported".
* Claim checking: each sentence of pasted text is matched to the closest source sentences; the AI judges support with an
  exact quote, or a transparent keyword overlap is used when the AI is unavailable.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from typing import Any, Callable

from app.services.gaps import facets as F

STYLES = ("thematic", "methodological", "chronological", "narrative")
DRAFT_TYPES = ("introduction", "related_work", "abstract", "research_questions", "proposal", "conclusion")
MARKER = re.compile(r"\[(\d{1,3}(?:\s*[,;–-]\s*\d{1,3})*)\]")
NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?%?")
SENTENCE = re.compile(r"(?<=[.!?؟۔])\s+")
WORD = re.compile(r"[\w][\w\-]{2,}", re.UNICODE)
STOP = F.STOP | {"there", "these", "which", "their", "about", "such", "have", "has", "had", "also", "into"}


def source_text(source: dict[str, Any]) -> str:
    return f"{source.get('title', '')}. {source.get('abstract') or ''}"


def cited_numbers(text: str) -> list[int]:
    numbers: list[int] = []
    for match in MARKER.finditer(text):
        for part in re.split(r"\s*[,;]\s*", match.group(1)):
            if re.match(r"^\d+\s*[–-]\s*\d+$", part):
                start, end = [int(value) for value in re.split(r"\s*[–-]\s*", part)]
                numbers.extend(range(start, min(end, start + 50) + 1))
            elif part.strip().isdigit():
                numbers.append(int(part))
    return numbers


# --------------------------------------------------------------------------- themes


_NEGATIVE = re.compile(r"\b(does not|did not|do not|no (?:significant |clear )?(?:improvement|effect|difference|gain)|fails? to|failed to|worse than|underperform\w*|not (?:improve|reduce|outperform)\w*)\b", re.I)
_POSITIVE = re.compile(r"\b(improv\w+|reduc\w+|outperform\w*|increas\w+|better than|gains?|effective|lower\w*|higher)\b", re.I)


def _direction(abstract: str | None) -> str | None:
    text = abstract or ""
    if _NEGATIVE.search(text):
        return "negative"
    if _POSITIVE.search(text):
        return "positive"
    return None


def themes(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Groups of sources that share a task, domain, method or dataset (the review's candidate themes).
    Each theme lists its source numbers, a quote per source and whether the reported results point the same way;
    "mixed" means at least one source reports no effect while another reports one (a contradiction to discuss)."""
    numbered = [(index + 1, source) for index, source in enumerate(sources) if source]
    found = {number: F.extract(str(number), source.get("title", ""), source.get("abstract")) for number, source in numbered}
    by_number = dict(numbered)
    index: dict[tuple[str, str], list[int]] = defaultdict(list)
    for number, facets in found.items():
        for kind in ("task", "domain", "method", "dataset"):
            for label in facets.labels(kind):
                index[(kind, label)].append(number)
    rows = []
    for (kind, label), members in index.items():
        members = sorted(set(members))
        if len(members) < 2 or len(members) == len(numbered) and len(numbered) > 3:
            continue  # a theme shared by every paper says nothing
        directions = {_direction(by_number[number].get("abstract")) for number in members} - {None}
        evidence = "mixed" if directions == {"positive", "negative"} else ("consistent" if directions else "unclear")
        quotes = [{"n": number, "text": found[number].hits.get(kind, {}).get(label, "")[:300]} for number in members[:4]]
        rows.append({"label": label, "kind": kind, "papers": members, "evidence": evidence, "quotes": [quote for quote in quotes if quote["text"]]})
    rows.sort(key=lambda row: (-len(row["papers"]), ("task", "domain", "method", "dataset").index(row["kind"]), row["label"]))
    chosen, seen = [], set()
    for row in rows:
        key = frozenset(row["papers"])
        if key in seen:
            continue  # the same papers under another name add nothing
        seen.add(key)
        chosen.append(row)
        if len(chosen) >= 12:
            break
    return chosen


def outline_from_themes(sources: list[dict[str, Any]], chosen: list[dict[str, Any]]) -> list[dict[str, Any]]:
    everyone = [index + 1 for index, source in enumerate(sources) if source]
    valid = set(everyone)
    sections = [{"heading": "Introduction", "purpose": "introduction", "papers": everyone}]
    for theme in chosen:
        papers = sorted({number for number in theme.get("papers", []) if number in valid})
        if papers and str(theme.get("label", "")).strip():
            sections.append({"heading": str(theme["label"]).strip()[:200], "purpose": "theme", "papers": papers})
    sections += [
        {"heading": "Gaps and future directions", "purpose": "gaps", "papers": everyone},
        {"heading": "Conclusion", "purpose": "conclusion", "papers": everyone},
    ]
    return sections


# --------------------------------------------------------------------------- outline


def outline(sources: list[dict[str, Any]], style: str) -> list[dict[str, Any]]:
    """Sections with the 1-based source numbers each should use. Sources are dicts with title/abstract/year."""
    numbered = [(index + 1, source) for index, source in enumerate(sources) if source]
    everyone = [number for number, _ in numbered]
    found = {number: F.extract(str(number), source.get("title", ""), source.get("abstract")) for number, source in numbered}

    def groups(kinds: tuple[str, ...], limit: int = 5) -> list[tuple[str, list[int]]]:
        index: dict[str, list[int]] = defaultdict(list)
        for number, facets in found.items():
            for kind in kinds:
                for label in facets.labels(kind):
                    index[label].append(number)
        chosen, covered = [], set()
        for label, members in sorted(index.items(), key=lambda pair: -len(pair[1])):
            if len(members) < 2 and len(index) > limit:
                continue
            if set(members) <= covered and len(chosen) >= 2:
                continue
            chosen.append((label, sorted(set(members))))
            covered |= set(members)
            if len(chosen) >= limit:
                break
        rest = [number for number in everyone if number not in covered]
        if rest:
            chosen.append(("Other approaches", rest))
        return chosen

    sections: list[dict[str, Any]] = [{"heading": "Introduction", "purpose": "introduction", "papers": everyone}]
    if style == "chronological":
        years = sorted({source.get("year") for _, source in numbered if source.get("year")})
        if years:
            span = max(1, math.ceil((years[-1] - years[0] + 1) / 3))
            start = years[0]
            while start <= years[-1]:
                end = start + span - 1
                members = [number for number, source in numbered if source.get("year") and start <= source["year"] <= end]
                if members:
                    sections.append({"heading": f"{start}–{end}" if end != start else str(start), "purpose": "period", "papers": members})
                start = end + 1
        undated = [number for number, source in numbered if not source.get("year")]
        if undated:
            sections.append({"heading": "Undated work", "purpose": "period", "papers": undated})
    elif style == "methodological":
        for label, members in groups(("method",)):
            sections.append({"heading": label, "purpose": "method", "papers": members})
    elif style == "thematic":
        for label, members in groups(("task", "domain", "method")):
            sections.append({"heading": label, "purpose": "theme", "papers": members})
    else:
        sections += [
            {"heading": "Background", "purpose": "background", "papers": everyone},
            {"heading": "Main findings", "purpose": "findings", "papers": everyone},
            {"heading": "Agreements and disagreements", "purpose": "debate", "papers": everyone},
        ]
    sections += [
        {"heading": "Gaps and future directions", "purpose": "gaps", "papers": everyone},
        {"heading": "Conclusion", "purpose": "conclusion", "papers": everyone},
    ]
    return sections


DRAFT_SECTIONS: dict[str, list[tuple[str, str]]] = {
    "introduction": [("Introduction", "introduction")],
    "related_work": [("Related work", "related_work")],
    "abstract": [("Abstract", "abstract")],
    "research_questions": [("Research questions", "research_questions")],
    "proposal": [("Background", "background"), ("Problem statement", "problem"), ("Objectives", "objectives"), ("Proposed methods", "methods"), ("Expected contribution", "contribution")],
    "conclusion": [("Conclusion", "conclusion")],
}


# --------------------------------------------------------------------------- section writing

WRITER_SYSTEM = (
    "You are an academic writing assistant. Write ONLY from the numbered sources provided (title and abstract of each paper). "
    "Every sentence that states a finding, number, method or claim must end with citation markers like [2] or [1, 4] that "
    "point to the sources it comes from. Never cite a number that is not in the list, never invent results, numbers, authors "
    "or papers. If the sources do not support something, do not write it. Write in the requested language and style. "
    "Reply as JSON: {\"text\": \"...\"} with paragraphs separated by a blank line."
)


def writer_validator(count: int) -> Callable[[str], bool]:
    def validate(text: str) -> bool:
        data = _json(text)
        body = data.get("text") if data else None
        if not isinstance(body, str) or len(body.strip()) < 40:
            return False
        numbers = cited_numbers(body)
        return bool(numbers) and all(1 <= number <= count for number in numbers)
    return validate


def _json(text: str) -> dict[str, Any] | None:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def write_section(*, heading: str, purpose: str, sources: list[dict[str, Any]], numbers: list[int], style: str, language: str, instruction: str = "", doc_title: str = "", outline_headings: list[str] | None = None) -> str:
    from app.services.ai_router import get_default_router

    allowed = [number for number in numbers if 1 <= number <= len(sources) and sources[number - 1]] or [index + 1 for index, source in enumerate(sources) if source]
    prompt = json.dumps({
        "document_title": doc_title,
        "section": heading,
        "purpose": purpose,
        "review_style": style,
        "language": language,
        "other_sections": outline_headings or [],
        "instruction": instruction[:600],
        "length": "120-260 words" if purpose not in {"abstract", "research_questions"} else "80-180 words",
        "sources": [{"n": number, "title": sources[number - 1].get("title"), "authors": (sources[number - 1].get("authors") or [])[:3], "year": sources[number - 1].get("year"), "abstract": (sources[number - 1].get("abstract") or "")[:1800]} for number in allowed[:25]],
    }, ensure_ascii=False)
    validate = writer_validator(len(sources))
    response = get_default_router().complete("summary", prompt, system=WRITER_SYSTEM, user_content=True, model_family="write:section", max_tokens=1100, validator=validate, language=language)
    data = _json(response.text)
    if not data or not validate(response.text):
        raise ValueError("invalid section")
    return re.sub(r"\n{3,}", "\n\n", data["text"].strip())


def unsupported_sentences(text: str, sources: list[dict[str, Any] | None]) -> list[str]:
    """Sentences with no citation, a citation to a missing source, or a number not found in the cited sources."""
    flagged = []
    for paragraph in re.split(r"\n\s*\n", text or ""):
        for sentence in SENTENCE.split(paragraph.strip()):
            clean = sentence.strip()
            if len(re.findall(r"\w+", MARKER.sub(" ", clean))) < 3:
                continue
            numbers = cited_numbers(clean)
            if not numbers or any(not (1 <= number <= len(sources)) or not sources[number - 1] for number in numbers):
                flagged.append(clean)
                continue
            cited = " ".join(source_text(sources[number - 1]) for number in numbers)
            claimed = [value.rstrip("%") for value in NUMBER.findall(MARKER.sub(" ", clean))]
            if any(value not in cited for value in claimed if len(value.replace(".", "").replace(",", "")) >= 2):
                flagged.append(clean)
    return flagged


# --------------------------------------------------------------------------- claim checking

JUDGE_SYSTEM = (
    "You check claims against evidence passages from research papers. For each claim decide: supported, conflicting, mixed "
    "or not_found, using ONLY the passages given for that claim. Give an exact quote copied from one passage, the passage's "
    "source number, an evidence strength (strong, moderate, limited) and, when the claim overstates the evidence, a safer "
    "rewording in the claim's language. Reply as JSON."
)
VERDICTS = ("supported", "conflicting", "mixed", "not_found")


def split_claims(text: str) -> list[str]:
    claims = []
    for paragraph in re.split(r"\n+", text or ""):
        for sentence in SENTENCE.split(paragraph.strip()):
            clean = sentence.strip()
            if len(WORD.findall(clean)) >= 5:
                claims.append(clean[:600])
    return claims[:40]


def candidate_passages(claim: str, sources: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    terms = {word.lower() for word in WORD.findall(claim)} - STOP
    passages = []
    for number, source in enumerate(sources, start=1):
        if not source:
            continue
        for sentence in [source.get("title", "")] + SENTENCE.split(re.sub(r"\s+", " ", source.get("abstract") or "")):
            words = {word.lower() for word in WORD.findall(sentence)}
            overlap = len(terms & words)
            if overlap:
                passages.append({"n": number, "text": sentence.strip()[:500], "score": overlap / (len(terms) or 1)})
    passages.sort(key=lambda item: -item["score"])
    return passages[:limit]


def keyword_verdicts(claims: list[str], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for claim in claims:
        passages = candidate_passages(claim, sources)
        best = passages[0] if passages else None
        supported = bool(best and best["score"] >= 0.5)
        results.append({
            "claim": claim,
            "verdict": "supported" if supported else "not_found",
            "strength": ("moderate" if best["score"] >= 0.7 else "limited") if supported else None,
            "evidence": [{"n": best["n"], "quote": best["text"]}] if supported else [],
            "safer": None,
        })
    return results


def judge_validator(batch: list[tuple[str, list[dict[str, Any]]]]) -> Callable[[str], bool]:
    def validate(text: str) -> bool:
        data = _json(text)
        rows = data.get("claims") if data else None
        if not isinstance(rows, list) or len(rows) != len(batch):
            return False
        for row, (_, passages) in zip(rows, batch):
            if not isinstance(row, dict) or row.get("verdict") not in VERDICTS:
                return False
            if row["verdict"] != "not_found":
                quote = re.sub(r"\s+", " ", str(row.get("quote") or "")).strip().lower()
                if len(quote) < 10 or not any(quote in re.sub(r"\s+", " ", passage["text"]).lower() and passage["n"] == row.get("n") for passage in passages):
                    return False
                if row.get("strength") not in ("strong", "moderate", "limited"):
                    return False
        return True
    return validate


def ai_verdicts(claims: list[str], sources: list[dict[str, Any]], language: str) -> list[dict[str, Any]]:
    from app.services.ai_router import get_default_router

    router = get_default_router()
    results: list[dict[str, Any]] = []
    for offset in range(0, len(claims), 8):
        batch = [(claim, candidate_passages(claim, sources)) for claim in claims[offset:offset + 8]]
        prompt = json.dumps({
            "language": language,
            "output_schema": {"claims": [{"verdict": "supported | conflicting | mixed | not_found", "n": 1, "quote": "exact words from that passage", "strength": "strong | moderate | limited", "safer": "optional safer wording"}]},
            "claims": [{"claim": claim, "passages": [{"n": passage["n"], "text": passage["text"]} for passage in passages]} for claim, passages in batch],
        }, ensure_ascii=False)
        validate = judge_validator(batch)
        response = router.complete("chat", prompt, system=JUDGE_SYSTEM, user_content=True, model_family="write:claims", max_tokens=1400, validator=validate, language=language)
        data = _json(response.text)
        if not data or not validate(response.text):
            raise ValueError("invalid verdicts")
        for row, (claim, _) in zip(data["claims"], batch):
            found = row["verdict"] != "not_found"
            results.append({
                "claim": claim,
                "verdict": row["verdict"],
                "strength": row.get("strength") if found else None,
                "evidence": [{"n": int(row["n"]), "quote": str(row["quote"]).strip()[:500]}] if found else [],
                "safer": (str(row.get("safer")).strip()[:600] or None) if row.get("safer") else None,
            })
    return results


def theme_counts(sources: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for number, source in enumerate(sources, start=1):
        if source:
            for kind in ("method", "task", "domain"):
                counts.update(F.extract(str(number), source.get("title", ""), source.get("abstract")).labels(kind))
    return dict(counts.most_common(10))
