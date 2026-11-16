"""Large-scale analytics over curated papers: trends, hot and emerging topics, citation patterns, source coverage,
collaboration and research-gap candidates.

The same metrics are produced by the Spark SQL job (spark/analytics_job.py) for big datasets; this module is the
reference implementation used by the local engine and the tests. Every output is evidence-based: counts, the papers
behind them and the formula used, so the UI can show *why* something is called "emerging" or a "gap".
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from itertools import combinations
from statistics import median
from typing import Any


def _percentile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return float(ordered[low] + (ordered[high] - ordered[low]) * (position - low))


def publication_trends(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    per_year: dict[int, dict[str, int]] = defaultdict(lambda: {"papers": 0, "citations": 0, "open_access": 0})
    for paper in papers:
        if paper.get("year"):
            row = per_year[paper["year"]]
            row["papers"] += 1
            row["citations"] += paper.get("citation_count") or 0
            row["open_access"] += 1 if paper.get("is_open_access") else 0
    return [{"year": year, **values} for year, values in sorted(per_year.items())]


def topic_trends(papers: list[dict[str, Any]], *, top: int = 15) -> list[dict[str, Any]]:
    totals: Counter[str] = Counter()
    by_year: dict[str, Counter[int]] = defaultdict(Counter)
    for paper in papers:
        for topic in set(paper.get("topics") or []):
            totals[topic] += 1
            if paper.get("year"):
                by_year[topic][paper["year"]] += 1
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:top]
    return [{"topic": topic, "total": count, "by_year": {str(year): n for year, n in sorted(by_year[topic].items())}} for topic, count in ranked]


def hot_topics(papers: list[dict[str, Any]], *, current_year: int, window: int = 2, min_recent: int = 3, top: int = 15) -> list[dict[str, Any]]:
    """Topics whose output grew most in the last `window` complete years versus the `window` years before.

    growth = (recent + 1) / (prior + 1) — the +1 keeps brand-new topics finite. A topic is "emerging" when it had at
    most one paper in the prior window and at least `min_recent` now; otherwise it is "growing" if growth ≥ 1.5.
    """
    last_complete = current_year - 1
    recent_years = set(range(last_complete - window + 1, last_complete + 1))
    prior_years = set(range(last_complete - 2 * window + 1, last_complete - window + 1))
    recent: Counter[str] = Counter()
    prior: Counter[str] = Counter()
    examples: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for paper in papers:
        year = paper.get("year")
        for topic in set(paper.get("topics") or []):
            if year in recent_years:
                recent[topic] += 1
                examples[topic].append((paper.get("citation_count") or 0, paper["paper_id"]))
            elif year in prior_years:
                prior[topic] += 1
    rows = []
    for topic, count in recent.items():
        if count < min_recent:
            continue
        growth = (count + 1) / (prior[topic] + 1)
        status = "emerging" if prior[topic] <= 1 else ("growing" if growth >= 1.5 else "steady")
        if status == "steady":
            continue
        rows.append({
            "topic": topic, "status": status, "recent": count, "prior": prior[topic], "growth": round(growth, 2),
            "recent_years": [min(recent_years), max(recent_years)], "prior_years": [min(prior_years), max(prior_years)],
            "example_paper_ids": [paper_id for _, paper_id in sorted(examples[topic], reverse=True)[:5]],
        })
    rows.sort(key=lambda row: (-row["growth"], -row["recent"], row["topic"]))
    return rows[:top]


def citation_patterns(papers: list[dict[str, Any]], *, top: int = 10) -> dict[str, Any]:
    per_year: dict[int, list[int]] = defaultdict(list)
    for paper in papers:
        if paper.get("year"):
            per_year[paper["year"]].append(paper.get("citation_count") or 0)
    all_counts = [paper.get("citation_count") or 0 for paper in papers]
    uncited = sum(1 for count in all_counts if count == 0)
    total = sum(all_counts)
    top_share = sum(sorted(all_counts, reverse=True)[: max(1, len(all_counts) // 10)]) / total if total else 0.0
    return {
        "by_year": [{"year": year, "median": median(values), "p90": _percentile(values, 0.9), "max": max(values), "papers": len(values)} for year, values in sorted(per_year.items())],
        "uncited_share": round(uncited / len(all_counts), 4) if all_counts else 0.0,
        "top_decile_share": round(top_share, 4),
        "most_cited": [
            {"paper_id": paper["paper_id"], "title": paper.get("title"), "year": paper.get("year"), "citation_count": paper.get("citation_count") or 0}
            for paper in sorted(papers, key=lambda p: (-(p.get("citation_count") or 0), p["paper_id"]))[:top]
        ],
    }


def source_coverage(papers: list[dict[str, Any]]) -> dict[str, Any]:
    per_source: Counter[str] = Counter()
    only_in: Counter[str] = Counter()
    by_count: Counter[int] = Counter()
    for paper in papers:
        sources = paper.get("sources") or []
        by_count[len(sources)] += 1
        for source in sources:
            per_source[source] += 1
        if len(sources) == 1:
            only_in[sources[0]] += 1
    return {
        "papers_per_source": dict(per_source),
        "unique_to_source": dict(only_in),
        "papers_by_source_count": {str(count): n for count, n in sorted(by_count.items())},
        "duplicates_merged": sum(paper.get("duplicate_count") or 0 for paper in papers),
    }


def collaboration(papers: list[dict[str, Any]], *, top: int = 15) -> dict[str, Any]:
    authors: Counter[str] = Counter()
    citations: Counter[str] = Counter()
    pairs: Counter[tuple[str, str]] = Counter()
    institutions: Counter[str] = Counter()
    team_sizes: list[int] = []
    for paper in papers:
        names = sorted({author["name"] for author in paper.get("authors") or [] if author.get("name")})
        team_sizes.append(len(names))
        for name in names:
            authors[name] += 1
            citations[name] += paper.get("citation_count") or 0
        for left, right in combinations(names[:25], 2):
            pairs[(left, right)] += 1
        for inst in {aff for author in paper.get("authors") or [] for aff in author.get("affiliations") or []}:
            institutions[inst] += 1
    return {
        "top_authors": [{"name": name, "papers": count, "citations": citations[name]} for name, count in authors.most_common(top)],
        "top_pairs": [{"authors": list(pair), "papers": count} for pair, count in pairs.most_common(top) if count > 1],
        "top_institutions": [{"name": name, "papers": count} for name, count in institutions.most_common(top)],
        "median_team_size": median(team_sizes) if team_sizes else 0,
    }


def gap_candidates(papers: list[dict[str, Any]], *, min_topic: int = 5, top: int = 15) -> list[dict[str, Any]]:
    """Topic pairs that are each well studied but rarely studied together (low lift).

    expected = n_a * n_b / N ; lift = observed / expected. A pair is a candidate when expected ≥ 2 and lift ≤ 0.35.
    The evidence (counts and example papers from each side) is returned so the claim can be checked; this is a
    starting point for investigation, not proof of a gap.
    """
    total = len(papers)
    if total < 10:
        return []
    topic_papers: dict[str, list[str]] = defaultdict(list)
    for paper in papers:
        for topic in set(paper.get("topics") or []):
            topic_papers[topic].append(paper["paper_id"])
    frequent = sorted([topic for topic, ids in topic_papers.items() if len(ids) >= min_topic], key=lambda t: (-len(topic_papers[t]), t))[:60]
    sets = {topic: set(topic_papers[topic]) for topic in frequent}
    rows = []
    for a, b in combinations(frequent, 2):
        if a.lower() in b.lower() or b.lower() in a.lower():
            continue
        observed = len(sets[a] & sets[b])
        expected = len(sets[a]) * len(sets[b]) / total
        if expected < 2:
            continue
        lift = observed / expected
        if lift <= 0.35:
            rows.append({
                "topics": [a, b], "papers_a": len(sets[a]), "papers_b": len(sets[b]), "together": observed,
                "expected": round(expected, 2), "lift": round(lift, 3),
                "evidence": {"a": sorted(sets[a])[:3], "b": sorted(sets[b])[:3], "together": sorted(sets[a] & sets[b])[:3]},
                "level": "strong" if expected >= 8 and observed == 0 else ("moderate" if expected >= 4 else "limited"),
            })
    rows.sort(key=lambda row: (row["lift"], -row["expected"]))
    return rows[:top]


def run_all(papers: list[dict[str, Any]], *, current_year: int) -> dict[str, Any]:
    return {
        "paper_count": len(papers),
        "publication_trends": publication_trends(papers),
        "topic_trends": topic_trends(papers),
        "hot_topics": hot_topics(papers, current_year=current_year),
        "citation_patterns": citation_patterns(papers),
        "source_coverage": source_coverage(papers),
        "collaboration": collaboration(papers),
        "gap_candidates": gap_candidates(papers),
    }
