"""Personalized recommendations (master prompt Part 15, Vision §15).

Candidates are ranked against the papers a user saved (and the limitations they noted). Every recommendation has
exactly one plain reason that points at something the user can check: the shared dataset, the saved paper it builds
on, or the limitation it addresses. No AI is used, so nothing user-owned leaves the server and results are stable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.gaps import facets as F
from app.services.gaps.analysis import Paper


def _norm_title(title: str) -> str:
    return re.sub(r"[^\w]+", " ", (title or "").lower()).strip()


@dataclass
class _Profile:
    paper: Paper
    datasets: set[str]
    methods: set[str]
    tasks: set[str]
    terms: set[str]


def _profile(paper: Paper) -> _Profile:
    found = F.extract(paper.id, paper.title, paper.abstract, datasets=paper.datasets, methods=paper.methods)
    terms = {term for term in F.key_terms(f"{paper.title}. {paper.abstract or ''}") if len(term) > 4}
    return _Profile(paper, found.labels("dataset"), found.labels("method"), found.labels("task"), terms)


def recommend(saved: list[Paper], candidates: list[Paper], *, notes: list[str] | None = None, current_year: int, limit: int = 10) -> list[dict[str, Any]]:
    if not saved or not candidates:
        return []
    saved_profiles = [_profile(paper) for paper in saved]
    saved_titles = {_norm_title(paper.title) for paper in saved}
    saved_doi_like = {paper.id for paper in saved}

    # Limitations the user cares about: stated in saved abstracts, or written in their notes.
    limitations: list[tuple[set[str], str]] = []
    for profile in saved_profiles:
        for sentence in F.limitation_sentences(profile.paper.abstract):
            terms = {term for term in F.key_terms(sentence) if len(term) > 4}
            if len(terms) >= 2:
                limitations.append((terms, profile.paper.title))
    for note in notes or []:
        terms = {term for term in F.key_terms(note) if len(term) > 4}
        if len(terms) >= 2:
            limitations.append((terms, ""))

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = _norm_title(candidate.title)
        if not key or key in saved_titles or candidate.id in saved_doi_like or key in seen:
            continue
        seen.add(key)
        profile = _profile(candidate)
        best: tuple[float, dict[str, Any]] | None = None
        for mine in saved_profiles:
            shared_datasets = sorted(profile.datasets & mine.datasets)
            shared_methods = sorted(profile.methods & mine.methods)
            shared_tasks = sorted(profile.tasks & mine.tasks)
            overlap = len(profile.terms & mine.terms)
            score = 3.0 * len(shared_datasets) + 2.0 * len(shared_methods) + 1.0 * len(shared_tasks) + min(overlap, 6) * 0.4
            if score < 2.0:
                continue
            newer = bool(candidate.year and mine.paper.year and candidate.year > mine.paper.year)
            if newer and shared_methods and (shared_tasks or shared_datasets):
                reason = {"kind": "extends", "paper_title": mine.paper.title, "label": shared_methods[0]}
                score += 1.5
            elif shared_datasets:
                reason = {"kind": "same_dataset", "paper_title": mine.paper.title, "label": shared_datasets[0]}
            elif shared_methods:
                reason = {"kind": "same_method", "paper_title": mine.paper.title, "label": shared_methods[0]}
            else:
                reason = {"kind": "similar_topic", "paper_title": mine.paper.title, "label": shared_tasks[0] if shared_tasks else ""}
            if best is None or score > best[0]:
                best = (score, reason)
        text_terms = {term for term in F.key_terms(f"{candidate.title}. {candidate.abstract or ''}") if len(term) > 4}
        for terms, source_title in limitations:
            hit = terms & text_terms
            if len(hit) >= 2 and len(hit) / len(terms) >= 0.5:
                score = 4.0 + len(hit) * 0.5
                if best is None or score > best[0]:
                    best = (score, {"kind": "addresses_limitation", "paper_title": source_title, "label": ", ".join(sorted(hit)[:3])})
                break
        if best is None:
            continue
        score, reason = best
        if candidate.year:
            score += max(0.0, 1.0 - 0.2 * max(0, current_year - candidate.year))
        score += min(1.0, (candidate.citation_count or 0) / 500)
        results.append({"paper_id": candidate.id, "score": round(score, 3), "reason": reason})
    results.sort(key=lambda row: (-row["score"], row["paper_id"]))
    for row in results:
        row.pop("score")
    return results[:limit]
