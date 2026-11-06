"""Ask your Library: answers grounded only in the owner's saved papers, notes and ideas.

1. Candidate memory is narrowed by any time phrase in the question ("last month", "last semester", "in 2024").
2. A BM25 ranking picks the most relevant papers and notes.
3. When the AI router is available, it writes a short answer that cites those sources as [1], [2] …; the answer is
   rejected unless every marker points to a source that was actually given. Otherwise the matches alone are returned.
The owner's notes are private content: the router is always called with user_content=True.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable

WORD = re.compile(r"[\w][\w\-]+", re.UNICODE)
STOP = {
    "the", "and", "for", "with", "that", "this", "from", "what", "which", "about", "into", "have", "has", "were", "was", "are", "you",
    "your", "my", "mine", "find", "show", "papers", "paper", "related", "problem", "worked", "work", "last", "this", "semester", "month",
    "week", "year", "years", "ago", "recent", "recently", "did", "does", "any", "all", "can", "how", "why", "when", "who", "where", "me",
    "i", "on", "in", "of", "to", "a", "an", "is", "it", "be", "do", "or", "by", "as", "at",
}
SYSTEM = (
    "You answer questions about the user's own research library. Use ONLY the numbered sources provided. "
    "Cite every claim with [n] markers that refer to those sources. If the sources do not answer the question, say so "
    "plainly and set not_found to true. Never invent papers, numbers or quotes. Reply in the requested language as JSON."
)


def time_window(question: str, today: date | None = None) -> tuple[date, date] | None:
    """A date range named in the question, or None. Covers the common English phrasings."""
    today = today or datetime.now(UTC).date()
    text = question.casefold()
    year = re.search(r"\b(?:in|during|from)\s+(20\d\d|19\d\d)\b", text)
    if year:
        value = int(year.group(1))
        return date(value, 1, 1), date(value, 12, 31)
    rules: list[tuple[str, Callable[[], tuple[date, date]]]] = [
        (r"\btoday\b", lambda: (today, today)),
        (r"\byesterday\b", lambda: (today - timedelta(days=1), today - timedelta(days=1))),
        (r"\b(?:this|past) week\b", lambda: (today - timedelta(days=7), today)),
        (r"\blast week\b", lambda: (today - timedelta(days=14), today - timedelta(days=7))),
        (r"\b(?:this|past) month\b", lambda: (today - timedelta(days=31), today)),
        (r"\blast month\b", lambda: (today - timedelta(days=62), today - timedelta(days=28))),
        (r"\b(?:this|current) semester\b", lambda: (today - timedelta(days=150), today)),
        (r"\blast semester\b|\bprevious semester\b", lambda: (today - timedelta(days=330), today - timedelta(days=120))),
        (r"\bthis year\b", lambda: (date(today.year, 1, 1), today)),
        (r"\blast year\b", lambda: (date(today.year - 1, 1, 1), date(today.year - 1, 12, 31))),
    ]
    for pattern, window in rules:
        if re.search(pattern, text):
            return window()
    return None


def _when(record: dict[str, Any]) -> date | None:
    value = record.get("updated_at") or record.get("added_at") or record.get("created_at")
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None


def build_sources(items: list[dict], notes: list[dict]) -> list[dict[str, Any]]:
    sources = []
    for item in items:
        text = " ".join(part for part in [item["title"], " ".join(item.get("authors") or []), item.get("venue") or "", item.get("abstract") or "", " ".join(item.get("tags") or [])] if part)
        sources.append({"kind": "paper", "id": item["id"], "title": item["title"], "text": text, "snippet": (item.get("abstract") or "")[:280], "when": _when(item), "year": item.get("year")})
    for note in notes:
        text = " ".join(part for part in [note.get("title") or "", note.get("body") or "", note.get("quote") or ""] if part)
        if text.strip():
            sources.append({"kind": note["kind"], "id": note["id"], "title": note.get("title") or (note.get("body") or "")[:80], "text": text, "snippet": (note.get("quote") or note.get("body") or "")[:280], "when": _when(note), "item_id": note.get("item_id")})
    return sources


def rank(sources: list[dict[str, Any]], question: str, limit: int = 8) -> list[dict[str, Any]]:
    terms = [word.casefold() for word in WORD.findall(question) if word.casefold() not in STOP and len(word) > 2]
    if not terms:
        return sorted(sources, key=lambda source: source["when"] or date.min, reverse=True)[:limit]
    documents = [Counter(word.casefold() for word in WORD.findall(source["text"])) for source in sources]
    count = len(documents) or 1
    average = sum(sum(document.values()) for document in documents) / count or 1
    scored = []
    for source, document in zip(sources, documents):
        length = sum(document.values()) or 1
        score = 0.0
        for term in set(terms):
            frequency = document.get(term, 0) + sum(value for word, value in document.items() if len(term) > 4 and word != term and word.startswith(term[:5])) * 0.5
            if not frequency:
                continue
            containing = sum(1 for other in documents if term in other) or 1
            idf = math.log(1 + (count - containing + 0.5) / (containing + 0.5))
            score += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / average))
        if source["text"] and source["title"] and any(term in source["title"].casefold() for term in terms):
            score *= 1.25
        if score > 0:
            scored.append((score, source))
    return [source for _, source in sorted(scored, key=lambda pair: pair[0], reverse=True)[:limit]]


def search_memory(items: list[dict], notes: list[dict], question: str, today: date | None = None) -> tuple[list[dict[str, Any]], bool]:
    """Ranked sources and whether a time window from the question was applied."""
    sources = build_sources(items, notes)
    window = time_window(question, today)
    if window:
        within = [source for source in sources if source["when"] and window[0] <= source["when"] <= window[1]]
        if within:
            # Papers related to what the owner worked on in that window: rank everything against that window's own words too.
            seed = " ".join(source["text"] for source in within)[:4000]
            ranked = rank(within, question) or within[:8]
            related = [source for source in rank(sources, f"{question} {seed}", limit=12) if source not in ranked]
            return (ranked + related)[:8], True
    return rank(sources, question), False


def _json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def validator_for(count: int) -> Callable[[str], bool]:
    def validate(text: str) -> bool:
        data = _json_object(text)
        if not data or not isinstance(data.get("answer"), str) or not data["answer"].strip():
            return False
        markers = [int(value) for value in re.findall(r"\[(\d{1,2})\]", data["answer"])]
        if data.get("not_found"):
            return all(1 <= marker <= count for marker in markers)
        return bool(markers) and all(1 <= marker <= count for marker in markers)
    return validate


def ai_answer(question: str, sources: list[dict[str, Any]], language: str) -> dict[str, Any]:
    """Raises on any failure; the caller falls back to matches only."""
    from app.services.ai_router import get_default_router

    router = get_default_router()
    numbered = "\n\n".join(f"[{index}] ({'paper' if source['kind'] == 'paper' else source['kind']}) {source['title']}\n{source['text'][:1500]}" for index, source in enumerate(sources, start=1))
    prompt = json.dumps({
        "question": question,
        "language": language,
        "output_schema": {"answer": "2-5 sentences with [n] markers", "not_found": False},
        "sources": numbered,
    }, ensure_ascii=False)
    validate = validator_for(len(sources))
    response = router.complete("chat", prompt, system=SYSTEM, user_content=True, model_family="library:ask", max_tokens=600, validator=validate, language=language)
    data = _json_object(response.text)
    if not data or not validate(response.text):
        raise ValueError("invalid answer")
    used = sorted({int(value) for value in re.findall(r"\[(\d{1,2})\]", data["answer"])})
    return {"answer": data["answer"].strip(), "not_found": bool(data.get("not_found")), "cited": used}
