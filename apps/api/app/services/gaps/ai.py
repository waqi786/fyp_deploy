"""AI steps for Gaps: Consensus (stance per paper) and AI hypotheses. Every output is validated against the papers:
quotes must appear in the paper's own text and hypotheses must cite papers that were given. On any failure the caller
falls back to a transparent keyword method (Consensus) or shows nothing (hypotheses)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable

from app.services.gaps.analysis import Paper

STANCES = ("supports", "opposes", "mixed", "not_addressed")
CONSENSUS_SYSTEM = (
    "You assess what each research paper says about a research question, using ONLY the paper's title and abstract. "
    "For every paper return a stance: supports, opposes, mixed or not_addressed; a one-sentence reason; and an exact quote "
    "copied from the abstract that shows it (empty when not_addressed). Never guess beyond the text. Reply as JSON."
)
HYPOTHESIS_SYSTEM = (
    "You propose research directions from a set of papers. Each direction must be grounded: cite at least two of the given "
    "paper ids that motivate it, and say in one sentence what evidence is missing. These are hypotheses for a researcher to "
    "check, not facts. Reply as JSON in the requested language."
)


def _json(text: str) -> dict[str, Any] | None:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _router():
    from app.services.ai_router import get_default_router

    return get_default_router()


# --------------------------------------------------------------------------- consensus

SUPPORT = re.compile(r"\b(improv\w*|increas\w*|outperform\w*|reduc\w*|effective|benefit\w*|higher|better|significant(?:ly)?|associated with)\b", re.I)
OPPOSE = re.compile(r"\b(no (?:significant )?(?:effect|difference|improvement)|did not|does not|failed to|worse|ineffective|no association|not associated|decreas\w* performance)\b", re.I)
WORD = re.compile(r"[\w][\w\-]{3,}", re.U)


def keyword_consensus(question: str, papers: list[Paper]) -> list[dict[str, Any]]:
    terms = {word.lower() for word in WORD.findall(question)} - {"which", "what", "does", "papers", "paper", "about", "there", "with", "that", "this", "have"}
    rows = []
    for paper in papers:
        best, best_score = "", 0
        for sentence in re.split(r"(?<=[.!?])\s+", paper.abstract or ""):
            score = sum(1 for term in terms if term in sentence.lower())
            if score > best_score:
                best, best_score = sentence.strip(), score
        if best_score < max(1, min(2, len(terms) // 2)):
            rows.append({"paper_id": paper.id, "stance": "not_addressed", "reason": "", "quote": ""})
            continue
        support, oppose = bool(SUPPORT.search(best)), bool(OPPOSE.search(best))
        stance = "mixed" if support and oppose else "opposes" if oppose else "supports" if support else "mixed"
        rows.append({"paper_id": paper.id, "stance": stance, "reason": "", "quote": best[:400]})
    return rows


def consensus_validator(papers: list[Paper]) -> Callable[[str], bool]:
    texts = {paper.id: _norm(f"{paper.title} {paper.abstract}") for paper in papers}

    def validate(text: str) -> bool:
        data = _json(text)
        rows = data.get("papers") if data else None
        if not isinstance(rows, list) or not rows:
            return False
        for row in rows:
            if not isinstance(row, dict) or row.get("paper_id") not in texts or row.get("stance") not in STANCES:
                return False
            quote = _norm(str(row.get("quote") or ""))
            if row["stance"] != "not_addressed" and (len(quote) < 12 or quote not in texts[row["paper_id"]]):
                return False
        return True
    return validate


def ai_consensus(question: str, papers: list[Paper], language: str) -> list[dict[str, Any]]:
    router = _router()
    rows: list[dict[str, Any]] = []
    for offset in range(0, len(papers), 12):
        batch = papers[offset:offset + 12]
        prompt = json.dumps({
            "question": question,
            "language_for_reasons": language,
            "output_schema": {"papers": [{"paper_id": "id", "stance": "supports | opposes | mixed | not_addressed", "reason": "one sentence", "quote": "exact words from the abstract"}]},
            "papers": [{"paper_id": paper.id, "title": paper.title, "abstract": (paper.abstract or "")[:2500]} for paper in batch],
        }, ensure_ascii=False)
        validate = consensus_validator(batch)
        response = router.complete("summary", prompt, system=CONSENSUS_SYSTEM, user_content=False, model_family="gaps:consensus", max_tokens=1600, validator=validate, language=language)
        data = _json(response.text)
        if not data or not validate(response.text):
            raise ValueError("invalid consensus")
        by_id = {row["paper_id"]: row for row in data["papers"]}
        for paper in batch:
            row = by_id.get(paper.id) or {"stance": "not_addressed", "reason": "", "quote": ""}
            rows.append({"paper_id": paper.id, "stance": row["stance"], "reason": str(row.get("reason") or "")[:300], "quote": str(row.get("quote") or "")[:400]})
    return rows


# --------------------------------------------------------------------------- hypotheses


def hypotheses_validator(ids: set[str]) -> Callable[[str], bool]:
    def validate(text: str) -> bool:
        data = _json(text)
        items = data.get("hypotheses") if data else None
        if not isinstance(items, list) or not items:
            return False
        for item in items:
            cited = item.get("paper_ids") if isinstance(item, dict) else None
            if not isinstance(item.get("title"), str) or not item["title"].strip() or not isinstance(cited, list) or len(set(cited) & ids) < 2 or not set(cited) <= ids:
                return False
        return True
    return validate


def ai_hypotheses(focus: str, papers: list[Paper], signals: list[dict[str, Any]], language: str) -> list[dict[str, Any]]:
    router = _router()
    ids = {paper.id for paper in papers}
    prompt = json.dumps({
        "focus": focus,
        "language": language,
        "output_schema": {"hypotheses": [{"title": "one-line research direction", "missing_evidence": "one sentence", "paper_ids": ["two or more ids"]}]},
        "observations": [{"kind": signal["kind"], "a": signal.get("a", {}).get("label"), "b": signal.get("b", {}).get("label"), "counts": signal.get("counts")} for signal in signals[:15]],
        "papers": [{"paper_id": paper.id, "title": paper.title, "year": paper.year, "abstract": (paper.abstract or "")[:700]} for paper in papers[:60]],
    }, ensure_ascii=False)
    validate = hypotheses_validator(ids)
    response = router.complete("summary", prompt, system=HYPOTHESIS_SYSTEM, user_content=False, model_family="gaps:hypotheses", max_tokens=900, validator=validate, language=language)
    data = _json(response.text)
    if not data or not validate(response.text):
        raise ValueError("invalid hypotheses")
    result = []
    for index, item in enumerate(data["hypotheses"][:5]):
        result.append({
            "id": "ai-" + hashlib.sha1(item["title"].strip().lower().encode("utf-8")).hexdigest()[:14],
            "kind": "ai_hypothesis",
            "level": "hypothesis",
            "a": {"kind": "theme", "label": item["title"].strip()[:240]},
            "detail": str(item.get("missing_evidence") or "").strip()[:400],
            "counts": {"a": len(set(item["paper_ids"]))},
            "papers": {"a": [paper_id for paper_id in item["paper_ids"] if paper_id in ids][:12]},
            "quotes": [],
        })
    return result
