"""Smart deduplication: merge the same paper found in several sources into one unified record.

Matching follows the order described in the project document — DOI first, then arXiv id, then title similarity
together with authors and year:

1. Exact identifiers. Records sharing a normalized DOI or arXiv id are the same work. An arXiv DOI
   (10.48550/arXiv.*) and the arXiv id are treated as the same identifier.
2. Fuzzy titles. Titles are MinHash-ed on character trigrams and bucketed with LSH, so only plausible pairs are
   compared (O(n) instead of O(n²)). A candidate pair is a duplicate when
     * title similarity ≥ 0.92, or ≥ 0.80 with at least one shared author family name, and
     * the years are compatible (≤ 1 year apart, or the preprint is up to 3 years older than the publication), and
     * the authors do not contradict each other (if both lists exist, they share a family name or a first author), and
     * they do not carry two different non-arXiv DOIs (two DOIs mean two published works).
3. Union-find turns matching pairs into clusters; each cluster becomes one curated paper.

Merging is field-by-field with a source priority and completeness rules (longest abstract, highest citation count,
published venue over arXiv, author list with most ORCIDs, union of topics). Every curated paper keeps the ids of the
records it came from, so the merge is auditable and reversible.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from resora_pipeline.text import MinHasher, author_last_name, char_shingles, is_arxiv_doi, stable_id, title_similarity

# Which source wins for each field when several records disagree (first wins).
FIELD_PRIORITY: dict[str, tuple[str, ...]] = {
    "title": ("crossref", "openalex", "semantic_scholar", "arxiv"),
    "venue": ("crossref", "openalex", "semantic_scholar", "arxiv"),
    "type": ("crossref", "openalex", "semantic_scholar", "arxiv"),
    "publication_date": ("crossref", "openalex", "semantic_scholar", "arxiv"),
    "language": ("openalex", "crossref", "semantic_scholar", "arxiv"),
}

TITLE_STRICT = 0.92
TITLE_WITH_AUTHORS = 0.80


@dataclass
class DedupStats:
    input_records: int = 0
    clusters: int = 0
    merged_records: int = 0
    by_rule: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    candidate_pairs: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "input_records": self.input_records,
            "unique_papers": self.clusters,
            "duplicates_merged": self.merged_records,
            "duplicate_rate": round(self.merged_records / self.input_records, 4) if self.input_records else 0.0,
            "candidate_pairs_checked": self.candidate_pairs,
            "matches_by_rule": dict(self.by_rule),
        }


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != root:  # path compression
            self.parent[item], item = root, self.parent[item]
        return root

    def union(self, left: int, right: int) -> bool:
        a, b = self.find(left), self.find(right)
        if a == b:
            return False
        if self.rank[a] < self.rank[b]:
            a, b = b, a
        self.parent[b] = a
        if self.rank[a] == self.rank[b]:
            self.rank[a] += 1
        return True


def _families(record: dict[str, Any]) -> list[str]:
    return [family for family in (author_last_name(author.get("name")) for author in record.get("authors") or []) if family]


def _years_compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    a, b = left.get("year"), right.get("year")
    if not a or not b:
        return True
    if abs(a - b) <= 1:
        return True
    # A preprint is often posted years before the journal version.
    preprint, published = (left, right) if left.get("source") == "arxiv" or left.get("type") == "preprint" else (right, left)
    if preprint.get("source") == "arxiv" or preprint.get("type") == "preprint":
        return 0 <= (published.get("year") or 0) - (preprint.get("year") or 0) <= 3
    return False


def _distinct_dois(left: dict[str, Any], right: dict[str, Any]) -> bool:
    a, b = left.get("doi"), right.get("doi")
    return bool(a and b and a != b and not is_arxiv_doi(a) and not is_arxiv_doi(b))


def match_rule(left: dict[str, Any], right: dict[str, Any]) -> str | None:
    """Return why two normalized records are the same paper ('doi', 'arxiv', 'title+authors', 'title'), or None."""
    if left.get("doi") and left.get("doi") == right.get("doi"):
        return "doi"
    if left.get("arxiv_id") and left.get("arxiv_id") == right.get("arxiv_id"):
        return "arxiv"
    if _distinct_dois(left, right) or not _years_compatible(left, right):
        return None
    similarity = title_similarity(left.get("title"), right.get("title"))
    if similarity < TITLE_WITH_AUTHORS:
        return None
    fam_a, fam_b = _families(left), _families(right)
    shared = bool(set(fam_a) & set(fam_b))
    if fam_a and fam_b and not shared and fam_a[0] != fam_b[0]:
        return None  # same title, different people: e.g. two theses with a generic title
    if similarity >= TITLE_STRICT:
        return "title+authors" if shared else "title"
    if shared:
        return "title+authors"
    return None


def _candidate_pairs(records: list[dict[str, Any]], hasher: MinHasher) -> set[tuple[int, int]]:
    buckets: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        title = record.get("title_norm") or ""
        if len(title) < 8:
            continue
        for key in hasher.band_keys(hasher.signature(char_shingles(title))):
            buckets[key].append(index)
    pairs: set[tuple[int, int]] = set()
    for members in buckets.values():
        if len(members) < 2 or len(members) > 200:  # a huge bucket is a degenerate title ("Introduction"); skip it
            continue
        for i, left in enumerate(members):
            for right in members[i + 1:]:
                pairs.add((left, right) if left < right else (right, left))
    return pairs


def cluster(records: list[dict[str, Any]], *, hasher: MinHasher | None = None) -> tuple[list[list[int]], DedupStats]:
    """Group record indices that refer to the same paper."""
    stats = DedupStats(input_records=len(records))
    union = UnionFind(len(records))
    by_identifier: dict[str, int] = {}
    for index, record in enumerate(records):
        for key in (f"doi:{record['doi']}" if record.get("doi") else None, f"arxiv:{record['arxiv_id']}" if record.get("arxiv_id") else None):
            if key is None:
                continue
            if key in by_identifier:
                if union.union(by_identifier[key], index):
                    stats.by_rule[key.split(":", 1)[0]] += 1
            else:
                by_identifier[key] = index
    pairs = _candidate_pairs(records, hasher or MinHasher())
    stats.candidate_pairs = len(pairs)
    for left, right in sorted(pairs):
        if union.find(left) == union.find(right):
            continue
        rule = match_rule(records[left], records[right])
        if rule and union.union(left, right):
            stats.by_rule[rule] += 1
    groups: dict[int, list[int]] = defaultdict(list)
    for index in range(len(records)):
        groups[union.find(index)].append(index)
    clusters = sorted(groups.values(), key=lambda members: members[0])
    stats.clusters = len(clusters)
    stats.merged_records = len(records) - len(clusters)
    return clusters, stats


def _by_priority(records: list[dict[str, Any]], key: str) -> Any:
    order = FIELD_PRIORITY.get(key, ())
    ranked = sorted(records, key=lambda record: order.index(record["source"]) if record["source"] in order else len(order))
    return next((record[key] for record in ranked if record.get(key)), None)


def merge(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge one cluster of normalized records into a curated paper."""
    dois = [record["doi"] for record in records if record.get("doi")]
    published_dois = [doi for doi in dois if not is_arxiv_doi(doi)]
    doi = (published_dois or dois or [None])[0]
    arxiv_id = next((record["arxiv_id"] for record in records if record.get("arxiv_id")), None)
    published = [record for record in records if record["source"] != "arxiv" and record.get("type") != "preprint"]
    years = [record["year"] for record in (published or records) if record.get("year")]
    authors = max((record.get("authors") or [] for record in records), key=lambda people: (sum(1 for a in people if a.get("orcid")), len(people)), default=[])
    orcids = {author_last_name(a["name"]): a["orcid"] for record in records for a in record.get("authors") or [] if a.get("orcid")}
    authors = [{**author, "orcid": author.get("orcid") or orcids.get(author_last_name(author.get("name")))} for author in authors]
    topics: dict[str, str] = {}
    for record in records:
        for topic in record.get("topics") or []:
            topics.setdefault(topic.lower(), topic)
    identity = doi or (f"arxiv:{arxiv_id}" if arxiv_id else None) or min(record["record_id"] for record in records)
    sources = sorted({record["source"] for record in records})
    venue = _by_priority(published, "venue") if published else None
    return {
        "paper_id": stable_id("rp_", identity),
        "doi": doi,
        "arxiv_id": arxiv_id,
        "title": _by_priority(records, "title"),
        "abstract": max((record.get("abstract") or "" for record in records), key=len),
        "year": min(years) if years else None,
        "publication_date": _by_priority(published or records, "publication_date"),
        "venue": venue or _by_priority(records, "venue"),
        "type": _by_priority(records, "type"),
        "authors": authors,
        "topics": list(topics.values())[:30],
        "citation_count": max((record.get("citation_count") or 0 for record in records), default=0),
        "reference_count": max((record.get("reference_count") or 0 for record in records), default=0),
        "is_open_access": any(record.get("is_open_access") for record in records),
        "oa_url": next((record["oa_url"] for record in records if record.get("oa_url")), None),
        "pdf_url": next((record["pdf_url"] for record in sorted(records, key=lambda r: r["source"] != "arxiv") if record.get("pdf_url")), None),
        "language": _by_priority(records, "language"),
        "sources": sources,
        "source_records": sorted(record["record_id"] for record in records),
        "duplicate_count": len(records) - 1,
    }


def deduplicate(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], DedupStats]:
    """Exact repeats of the same source record are collapsed first (latest fetch wins), then papers are clustered."""
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        current = latest.get(record["record_id"])
        if current is None or str(record.get("fetched_at") or "") >= str(current.get("fetched_at") or ""):
            latest[record["record_id"]] = record
    unique_records = list(latest.values())
    clusters, stats = cluster(unique_records)
    papers = [merge([unique_records[index] for index in members]) for members in clusters]
    papers.sort(key=lambda paper: paper["paper_id"])
    return papers, stats
