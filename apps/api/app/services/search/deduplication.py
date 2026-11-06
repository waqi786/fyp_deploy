import re
import string
from collections import Counter
from dataclasses import dataclass

from app.schemas.paper import PaperRecord

DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+", re.IGNORECASE)


def extract_doi(paper: PaperRecord) -> str | None:
    candidates = [
        paper.doi,
        paper.external_ids.get("DOI"),
        paper.url,
        paper.pdf_url,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        match = DOI_PATTERN.search(candidate)
        if match:
            return match.group(0).lower()
    return None


def normalize_title(title: str) -> str:
    lowered = title.lower().strip()
    table = str.maketrans("", "", string.punctuation)
    cleaned = lowered.translate(table)
    return re.sub(r"\s+", " ", cleaned).strip()


def score_paper_richness(paper: PaperRecord) -> int:
    score = 0
    if paper.abstract and len(paper.abstract.strip()) > 50:
        score += 3
    if paper.citation_count > 0:
        score += 2
    if paper.pdf_url:
        score += 2
    if paper.is_open_access:
        score += 1
    if paper.year:
        score += 1
    return score


def merge_papers(base: PaperRecord, candidate: PaperRecord) -> PaperRecord:
    merged = base.model_copy(deep=True)
    for field in (
        "abstract",
        "year",
        "venue",
        "doi",
        "url",
        "pdf_url",
    ):
        if not getattr(merged, field) and getattr(candidate, field):
            setattr(merged, field, getattr(candidate, field))
    merged.citation_count = max(merged.citation_count, candidate.citation_count)
    merged.reference_count = max(merged.reference_count, candidate.reference_count)
    merged.is_open_access = merged.is_open_access or candidate.is_open_access
    merged.authors = merged.authors or candidate.authors
    merged.external_ids.update(candidate.external_ids)
    merged.all_sources = sorted(set((merged.all_sources or [merged.source]) + [merged.source, candidate.source]))
    return merged


@dataclass
class DeduplicationResult:
    papers: list[PaperRecord]
    duplicates_removed: int
    likely_duplicate_pairs: list[list[str]]


def _tokenize_for_similarity(text: str) -> Counter[str]:
    tokens = re.findall(r"\b[a-zA-Z][a-zA-Z-]+\b", text.lower())
    return Counter(tokens)


def _jaccard_similarity(left: Counter[str], right: Counter[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    union = left_set | right_set
    if not union:
        return 0.0
    return len(left_set & right_set) / len(union)


def _author_names(paper: PaperRecord) -> set[str]:
    names = set()
    for author in paper.authors:
        name = (author.get("name") or "").strip().lower()
        if name:
            names.add(name)
    return names


def _semantic_duplicate_score(left: PaperRecord, right: PaperRecord) -> float:
    left_title = normalize_title(left.title)
    right_title = normalize_title(right.title)
    left_title_tokens = _tokenize_for_similarity(left_title)
    right_title_tokens = _tokenize_for_similarity(right_title)
    title_similarity = _jaccard_similarity(left_title_tokens, right_title_tokens)

    left_text = _tokenize_for_similarity(f"{left.title} {left.abstract or ''}")
    right_text = _tokenize_for_similarity(f"{right.title} {right.abstract or ''}")
    text_similarity = _jaccard_similarity(left_text, right_text)

    left_authors = _author_names(left)
    right_authors = _author_names(right)
    author_overlap = 1.0 if left_authors and right_authors and (left_authors & right_authors) else 0.0

    year_proximity = 1.0
    if left.year and right.year:
        year_gap = abs(left.year - right.year)
        year_proximity = 1.0 if year_gap == 0 else 0.6 if year_gap == 1 else 0.0

    return round((0.45 * title_similarity) + (0.35 * text_similarity) + (0.1 * author_overlap) + (0.1 * year_proximity), 3)


def _find_semantic_duplicate(candidate: PaperRecord, existing_papers: list[PaperRecord]) -> PaperRecord | None:
    best_match: PaperRecord | None = None
    best_score = 0.0
    for existing in existing_papers:
        score = _semantic_duplicate_score(candidate, existing)
        if score > best_score:
            best_score = score
            best_match = existing

    if best_match is None:
        return None

    title_similarity = _jaccard_similarity(
        _tokenize_for_similarity(normalize_title(candidate.title)),
        _tokenize_for_similarity(normalize_title(best_match.title)),
    )
    if best_score >= 0.86:
        return best_match
    if best_score >= 0.76 and title_similarity >= 0.6:
        return best_match
    return None


def deduplicate_papers(papers: list[PaperRecord]) -> DeduplicationResult:
    seen_by_doi: dict[str, PaperRecord] = {}
    seen_by_title: dict[str, PaperRecord] = {}
    result: list[PaperRecord] = []
    duplicates_removed = 0
    likely_duplicate_pairs: list[list[str]] = []

    for paper in papers:
        paper.all_sources = sorted(set((paper.all_sources or []) + [paper.source]))
        doi = extract_doi(paper)
        title_key = normalize_title(paper.title)

        existing = None
        if doi and doi in seen_by_doi:
            existing = seen_by_doi[doi]
        elif len(title_key) >= 10 and title_key in seen_by_title:
            existing = seen_by_title[title_key]
        else:
            existing = _find_semantic_duplicate(paper, result)

        if existing is None:
            result.append(paper)
            if doi:
                seen_by_doi[doi] = paper
            if len(title_key) >= 10:
                seen_by_title[title_key] = paper
            continue

        richer, poorer = (
            (paper, existing)
            if score_paper_richness(paper) > score_paper_richness(existing)
            else (existing, paper)
        )
        merged = merge_papers(richer, poorer)

        result = [merged if item.paper_id == existing.paper_id else item for item in result]
        merged_doi = extract_doi(merged)
        merged_title_key = normalize_title(merged.title)
        if merged_doi:
            seen_by_doi[merged_doi] = merged
        if len(merged_title_key) >= 10:
            seen_by_title[merged_title_key] = merged
        duplicates_removed += 1

    for index, left in enumerate(result):
        left_tokens = _tokenize_for_similarity((left.abstract or "") + " " + left.title)
        if not left_tokens:
            continue
        for right in result[index + 1:]:
            right_tokens = _tokenize_for_similarity((right.abstract or "") + " " + right.title)
            if not right_tokens:
                continue
            if _jaccard_similarity(left_tokens, right_tokens) >= 0.82:
                likely_duplicate_pairs.append([left.paper_id, right.paper_id])

    return DeduplicationResult(
        papers=result,
        duplicates_removed=duplicates_removed,
        likely_duplicate_pairs=likely_duplicate_pairs,
    )
