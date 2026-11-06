"""Gap signals, trends, people and datasets computed from a set of papers.

A signal is an observation about the evidence, never a verdict ("this is the gap"). Each one carries:
  * an evidence level — strong / moderate / limited — derived only from how many papers back it;
  * the counts and the ids of the papers behind every count, so the user can open them;
  * short quotes from the papers where the facet was found.
Signal ids are stable hashes of their content, so saved / dismissed states survive a re-run.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from app.services.gaps import facets as F

CONTEXT_KINDS = ("domain", "task", "population", "language", "dataset")


@dataclass
class Paper:
    id: str
    title: str
    abstract: str = ""
    year: int | None = None
    venue: str | None = None
    authors: list[str] = field(default_factory=list)
    institutions: list[str] = field(default_factory=list)
    citation_count: int = 0
    datasets: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    study_type: str | None = None
    sample_size: int | None = None
    is_open_access: bool = False


def _sid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).lower().encode("utf-8")).hexdigest()[:16]


def _level(counts: list[int], strong: int, moderate: int) -> str:
    low = min(counts) if counts else 0
    if low >= strong:
        return "strong"
    if low >= moderate:
        return "moderate"
    return "limited"


def _by(papers_facets: dict[str, F.PaperFacets], kind: str) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for paper_id, found in papers_facets.items():
        for label in found.labels(kind):
            index[label].append(paper_id)
    return index


def _quote(papers_facets: dict[str, F.PaperFacets], paper_id: str, kind: str, label: str) -> dict[str, str]:
    return {"paper_id": paper_id, "text": papers_facets[paper_id].hits.get(kind, {}).get(label, "")}


def analyze(papers: list[Paper], *, current_year: int) -> dict[str, Any]:
    found = {paper.id: F.extract(paper.id, paper.title, paper.abstract, datasets=paper.datasets, methods=paper.methods) for paper in papers}
    total = len(papers)
    signals: list[dict[str, Any]] = []
    methods = _by(found, "method")
    min_method = max(2, round(total * 0.08))

    # 1. Untested / thinly tested combinations: a common method and a common context that rarely meet.
    for method, method_ids in sorted(methods.items(), key=lambda pair: -len(pair[1])):
        if len(method_ids) < min_method:
            continue
        for kind in CONTEXT_KINDS:
            for context, context_ids in _by(found, kind).items():
                if len(context_ids) < 2 or context.lower() == method.lower():
                    continue
                both = sorted(set(method_ids) & set(context_ids))
                if len(both) > 1:
                    continue
                kind_name = "combination_untested" if not both else "combination_thin"
                quotes = [_quote(found, paper_id, "method", method) for paper_id in method_ids[:1]] + [_quote(found, paper_id, kind, context) for paper_id in context_ids[:1]]
                signals.append({
                    "id": _sid("combo", method, kind, context),
                    "kind": kind_name,
                    "level": _level([len(method_ids), len(context_ids)], 8, 4),
                    "a": {"kind": "method", "label": method},
                    "b": {"kind": kind, "label": context},
                    "counts": {"a": len(method_ids), "b": len(context_ids), "both": len(both)},
                    "papers": {"a": method_ids[:12], "b": context_ids[:12], "both": both},
                    "quotes": [quote for quote in quotes if quote["text"]],
                    "weight": min(len(method_ids), len(context_ids)) * (1.5 if not both else 1.0),
                })

    # 2. Missing head-to-heads: two common methods used for the same task or dataset but never in one paper.
    contexts = {paper_id: found[paper_id].labels("task") | found[paper_id].labels("dataset") for paper_id in found}
    common_methods = [(method, ids) for method, ids in methods.items() if len(ids) >= max(3, min_method)]
    for (left, left_ids), (right, right_ids) in combinations(common_methods, 2):
        if set(left_ids) & set(right_ids):
            continue
        shared = set().union(*(contexts[paper_id] for paper_id in left_ids)) & set().union(*(contexts[paper_id] for paper_id in right_ids))
        if not shared:
            continue
        signals.append({
            "id": _sid("h2h", *sorted([left, right])),
            "kind": "head_to_head",
            "level": _level([len(left_ids), len(right_ids)], 8, 4),
            "a": {"kind": "method", "label": left},
            "b": {"kind": "method", "label": right},
            "shared": sorted(shared)[:5],
            "counts": {"a": len(left_ids), "b": len(right_ids), "both": 0},
            "papers": {"a": left_ids[:12], "b": right_ids[:12], "both": []},
            "quotes": [_quote(found, left_ids[0], "method", left), _quote(found, right_ids[0], "method", right)],
            "weight": min(len(left_ids), len(right_ids)) * 1.2,
        })

    # 3. Repeated limitations: the same limitation themes stated by several papers.
    limitation_terms: dict[str, dict[str, str]] = defaultdict(dict)  # term -> paper_id -> sentence
    for paper in papers:
        for sentence in F.limitation_sentences(paper.abstract):
            inside = F.extract(paper.id, "", sentence, include_limitations=True)
            labels = {label for kind in ("domain", "task", "population", "language", "dataset", "method") for label in inside.labels(kind)}
            for term in labels or {term for term in F.key_terms(sentence) if len(term) > 5}:
                limitation_terms[term].setdefault(paper.id, sentence)
    # Terms stated by exactly the same papers describe one limitation: merge them into one signal.
    merged: dict[frozenset[str], list[str]] = defaultdict(list)
    for term, by_paper in limitation_terms.items():
        if len(by_paper) >= 2:
            merged[frozenset(by_paper)].append(term)
    for paper_ids, terms in sorted(merged.items(), key=lambda pair: (-len(pair[0]), sorted(pair[1]))):
        terms = sorted(terms, key=lambda term: (not term[:1].isupper(), -len(term), term))
        by_paper = limitation_terms[terms[0]]
        label = " · ".join(terms[:3])
        signals.append({
            "id": _sid("limit", *sorted(terms)),
            "kind": "repeated_limitation",
            "level": _level([len(by_paper)], 5, 3),
            "a": {"kind": "theme", "label": label},
            "counts": {"a": len(by_paper)},
            "papers": {"a": sorted(paper_ids, key=list(by_paper).index)[:12]},
            "quotes": [{"paper_id": paper_id, "text": sentence[:400]} for paper_id, sentence in list(by_paper.items())[:4]],
            "weight": len(by_paper) * 1.4,
        })

    # 4. Benchmark concentration: one dataset carries most of the evaluation.
    datasets = _by(found, "dataset")
    with_datasets = {paper_id for ids in datasets.values() for paper_id in ids}
    for dataset, ids in datasets.items():
        share = len(ids) / max(1, len(with_datasets))
        if len(ids) >= 3 and share >= 0.4 and len(with_datasets) >= 4:
            signals.append({
                "id": _sid("bench", dataset),
                "kind": "benchmark_concentration",
                "level": _level([len(ids)], 10, 5),
                "a": {"kind": "dataset", "label": dataset},
                "counts": {"a": len(ids), "of": len(with_datasets), "share": round(share * 100)},
                "papers": {"a": ids[:12]},
                "quotes": [_quote(found, paper_id, "dataset", dataset) for paper_id in ids[:2]],
                "weight": len(ids) * share,
            })

    # 5. Growing but thin: a facet whose recent share has doubled, still backed by few papers.
    years = {paper.id: paper.year for paper in papers if paper.year}
    if len(years) >= 6:
        recent_from = current_year - 2
        recent = {paper_id for paper_id, year in years.items() if year >= recent_from}
        older = set(years) - recent
        if recent and older:
            for kind in ("method", "task", "dataset", "language", "population"):
                for label, ids in _by(found, kind).items():
                    new = len(set(ids) & recent)
                    old = len(set(ids) & older)
                    if new >= 2 and new / len(recent) >= 2 * (old / len(older) if older else 0) + 0.05 and len(ids) <= max(3, total * 0.25):
                        signals.append({
                            "id": _sid("trend", kind, label),
                            "kind": "growing_thin",
                            "level": _level([len(ids)], 10, 4),
                            "a": {"kind": kind, "label": label},
                            "counts": {"a": len(ids), "recent": new, "since": recent_from},
                            "papers": {"a": ids[:12]},
                            "quotes": [_quote(found, paper_id, kind, label) for paper_id in sorted(set(ids) & recent)[:2]],
                            "weight": new * 1.1,
                        })

    seen: set[str] = set()
    unique = []
    for signal in sorted(signals, key=lambda item: -item["weight"]):
        if signal["id"] in seen:
            continue
        seen.add(signal["id"])
        signal.pop("weight", None)
        unique.append(signal)
    return {
        "paper_count": total,
        "signals": unique[:60],
        "trends": trends(papers, found),
        "people": people(papers, found),
        "datasets": dataset_table(papers, found),
    }


def trends(papers: list[Paper], found: dict[str, F.PaperFacets]) -> dict[str, Any]:
    by_year = Counter(paper.year for paper in papers if paper.year)
    citations = Counter()
    for paper in papers:
        if paper.year:
            citations[paper.year] += max(0, paper.citation_count or 0)
    years = sorted(by_year)
    series: dict[str, list[dict[str, Any]]] = {}
    for kind in ("method", "dataset", "task"):
        index = _by(found, kind)
        top = sorted(index.items(), key=lambda pair: -len(pair[1]))[:6]
        series[kind] = [
            {"label": label, "total": len(ids), "by_year": {str(year): sum(1 for paper_id in ids if next((paper.year for paper in papers if paper.id == paper_id), None) == year) for year in years}}
            for label, ids in top
        ]
    words = Counter()
    for paper in papers:
        for word in {word.rstrip("s") for word in re.findall(r"[a-z][a-z\-]{4,}", paper.title.lower())} - F.STOP:
            words[word] += 1
    return {
        "years": [{"year": year, "papers": by_year[year], "citations": citations[year]} for year in years],
        "series": series,
        "keywords": [{"label": word, "count": count} for word, count in words.most_common(15) if count >= 2],
    }


def people(papers: list[Paper], found: dict[str, F.PaperFacets] | None = None) -> dict[str, Any]:
    authors: dict[str, dict[str, Any]] = {}
    pairs = Counter()
    institutions = Counter()
    for paper in papers:
        names = [re.sub(r"\s+", " ", name).strip() for name in paper.authors if name and name.strip()]
        for name in names:
            entry = authors.setdefault(name, {"name": name, "papers": 0, "citations": 0, "years": set(), "paper_ids": []})
            entry["papers"] += 1
            entry["citations"] += max(0, paper.citation_count or 0)
            if paper.year:
                entry["years"].add(paper.year)
            entry["paper_ids"].append(paper.id)
        for left, right in combinations(sorted(set(names)), 2):
            pairs[(left, right)] += 1
        for institution in {value.strip() for value in paper.institutions if value and value.strip()}:
            institutions[institution] += 1
    ranked = sorted(authors.values(), key=lambda entry: (-entry["papers"], -entry["citations"], entry["name"]))[:25]
    result = []
    for entry in ranked:
        partners = Counter()
        for (left, right), count in pairs.items():
            if entry["name"] in (left, right):
                partners[right if left == entry["name"] else left] += count
        result.append({
            "name": entry["name"], "papers": entry["papers"], "citations": entry["citations"],
            "first_year": min(entry["years"]) if entry["years"] else None, "last_year": max(entry["years"]) if entry["years"] else None,
            "collaborators": [name for name, _ in partners.most_common(3)], "paper_ids": entry["paper_ids"][:10],
        })
    # Collaborator suggestions: active researchers who work on the same methods, datasets or tasks but have never
    # written a paper together in this set. Each suggestion names what they share, so it can be checked.
    if found:
        topics: dict[str, set[str]] = {}
        for entry in ranked:
            labels: set[str] = set()
            for paper_id in entry["paper_ids"]:
                facets = found.get(paper_id)
                if facets:
                    for kind in ("method", "dataset", "task"):
                        labels |= facets.labels(kind)
            topics[entry["name"]] = labels
        coauthors = {pair for pair in pairs}
        for row in result:
            mine = topics.get(row["name"], set())
            options = []
            for other in ranked:
                name = other["name"]
                if name == row["name"] or tuple(sorted((name, row["name"]))) in coauthors:
                    continue
                shared = sorted(mine & topics.get(name, set()))
                if len(shared) >= 2:
                    options.append((len(shared), other["papers"], name, shared[:3]))
            options.sort(key=lambda option: (-option[0], -option[1], option[2]))
            row["suggested"] = [{"name": name, "shared": shared} for _, _, name, shared in options[:3]]
    return {"researchers": result, "institutions": [{"name": name, "papers": count} for name, count in institutions.most_common(15)]}


def dataset_table(papers: list[Paper], found: dict[str, F.PaperFacets]) -> list[dict[str, Any]]:
    rows = []
    for dataset, ids in sorted(_by(found, "dataset").items(), key=lambda pair: -len(pair[1]))[:30]:
        members = [paper for paper in papers if paper.id in set(ids)]
        tasks = Counter(label for paper_id in ids for label in found[paper_id].labels("task"))
        methods = Counter(label for paper_id in ids for label in found[paper_id].labels("method"))
        metrics = Counter(label for paper_id in ids for label in found[paper_id].labels("metric"))
        sizes = [paper.sample_size for paper in members if paper.sample_size]
        years = [paper.year for paper in members if paper.year]
        rows.append({
            "name": dataset,
            "papers": len(ids),
            "paper_ids": ids[:12],
            "tasks": [label for label, _ in tasks.most_common(3)],
            "methods": [label for label, _ in methods.most_common(3)],
            "metrics": [label for label, _ in metrics.most_common(3)],
            "sample_size": max(sizes) if sizes else None,
            "first_year": min(years) if years else None,
            "last_year": max(years) if years else None,
            "open_access_papers": sum(1 for paper in members if paper.is_open_access),
            "quote": found[ids[0]].hits.get("dataset", {}).get(dataset, ""),
        })
    return rows
