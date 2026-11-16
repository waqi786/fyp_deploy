"""Map raw records from each source onto one common schema (the "normalized record").

A normalized record is a plain dict so it can be serialized to JSON lines, shipped to Spark executors and written to
Parquet without custom classes:

    record_id, source, source_id, doi, arxiv_id, title, title_norm, abstract, year, publication_date, venue, type,
    authors[{name, orcid, affiliations[]}], topics[], citation_count, reference_count, is_open_access, oa_url, pdf_url,
    language, updated_at, fetched_at

Raw records arrive wrapped in an envelope written by the collectors: {"source", "fetched_at", "query", "raw"}.
Records without a usable title are dropped (returned as None) and counted by the caller.
"""

from __future__ import annotations

from typing import Any

from resora_pipeline.text import normalize_arxiv_id, normalize_doi, normalize_title, strip_markup

SOURCES = ("openalex", "arxiv", "crossref", "semantic_scholar")


def _year(value: Any) -> int | None:
    try:
        year = int(str(value)[:4])
    except (TypeError, ValueError):
        return None
    return year if 1500 <= year <= 2200 else None


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _clean_topics(values: list[Any]) -> list[str]:
    seen: dict[str, str] = {}
    for value in values:
        label = strip_markup(value if isinstance(value, str) else (value or {}).get("display_name") or (value or {}).get("category") or "")
        if label and label.lower() not in seen:
            seen[label.lower()] = label
    return list(seen.values())[:25]


def _abstract_from_inverted_index(index: Any) -> str:
    if not isinstance(index, dict) or not index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, places in index.items():
        if isinstance(places, list):
            positions.extend((place, word) for place in places if isinstance(place, int))
    return " ".join(word for _, word in sorted(positions))


def _base(source: str, source_id: str, fetched_at: str | None) -> dict[str, Any]:
    return {
        "record_id": f"{source}:{source_id}",
        "source": source,
        "source_id": source_id,
        "doi": None,
        "arxiv_id": None,
        "title": "",
        "title_norm": "",
        "abstract": "",
        "year": None,
        "publication_date": None,
        "venue": None,
        "type": None,
        "authors": [],
        "topics": [],
        "citation_count": 0,
        "reference_count": 0,
        "is_open_access": False,
        "oa_url": None,
        "pdf_url": None,
        "language": None,
        "updated_at": None,
        "fetched_at": fetched_at,
    }


def _finish(record: dict[str, Any]) -> dict[str, Any] | None:
    record["title"] = strip_markup(record["title"])[:1000]
    record["title_norm"] = normalize_title(record["title"])
    record["abstract"] = strip_markup(record["abstract"])[:20000]
    if len(record["title_norm"]) < 4:
        return None
    if record["doi"] and record["doi"].startswith("10.48550/arxiv.") and not record["arxiv_id"]:
        record["arxiv_id"] = normalize_arxiv_id(record["doi"])
    return record


def from_openalex(raw: dict[str, Any], fetched_at: str | None = None) -> dict[str, Any] | None:
    source_id = str(raw.get("id") or "").rsplit("/", 1)[-1]
    if not source_id:
        return None
    record = _base("openalex", source_id, fetched_at)
    ids = raw.get("ids") if isinstance(raw.get("ids"), dict) else {}
    primary = raw.get("primary_location") if isinstance(raw.get("primary_location"), dict) else {}
    best = raw.get("best_oa_location") if isinstance(raw.get("best_oa_location"), dict) else {}
    source_info = primary.get("source") if isinstance(primary.get("source"), dict) else {}
    oa = raw.get("open_access") if isinstance(raw.get("open_access"), dict) else {}
    authors = []
    for authorship in raw.get("authorships") or []:
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author") if isinstance(authorship.get("author"), dict) else {}
        name = author.get("display_name") or authorship.get("raw_author_name")
        if name:
            authors.append({
                "name": strip_markup(name),
                "orcid": (author.get("orcid") or "").rsplit("/", 1)[-1] or None,
                "affiliations": [inst.get("display_name") for inst in authorship.get("institutions") or [] if isinstance(inst, dict) and inst.get("display_name")],
            })
    record.update({
        "doi": normalize_doi(raw.get("doi") or ids.get("doi")),
        "arxiv_id": normalize_arxiv_id(ids.get("arxiv")) if ids.get("arxiv") else None,
        "title": raw.get("title") or raw.get("display_name") or "",
        "abstract": _abstract_from_inverted_index(raw.get("abstract_inverted_index")),
        "year": _year(raw.get("publication_year")),
        "publication_date": raw.get("publication_date"),
        "venue": source_info.get("display_name"),
        "type": raw.get("type"),
        "authors": authors,
        "topics": _clean_topics([*(raw.get("topics") or []), *(raw.get("concepts") or [])[:8], *(raw.get("keywords") or [])]),
        "citation_count": _int(raw.get("cited_by_count")),
        "reference_count": _int(raw.get("referenced_works_count")),
        "is_open_access": bool(oa.get("is_oa")),
        "oa_url": oa.get("oa_url") or best.get("landing_page_url"),
        "pdf_url": best.get("pdf_url") or primary.get("pdf_url"),
        "language": raw.get("language"),
        "updated_at": raw.get("updated_date"),
    })
    return _finish(record)


def from_arxiv(raw: dict[str, Any], fetched_at: str | None = None) -> dict[str, Any] | None:
    arxiv_id = normalize_arxiv_id(raw.get("id"))
    if not arxiv_id:
        return None
    record = _base("arxiv", arxiv_id, fetched_at)
    published = raw.get("published") or ""
    record.update({
        "doi": normalize_doi(raw.get("doi")),
        "arxiv_id": arxiv_id,
        "title": raw.get("title") or "",
        "abstract": raw.get("summary") or "",
        "year": _year(published),
        "publication_date": published[:10] or None,
        "venue": raw.get("journal_ref") or "arXiv",
        "type": "preprint",
        "authors": [{"name": strip_markup(a.get("name")), "orcid": None, "affiliations": [x for x in [a.get("affiliation")] if x]} for a in raw.get("authors") or [] if isinstance(a, dict) and a.get("name")],
        "topics": _clean_topics(raw.get("categories") or []),
        "is_open_access": True,
        "oa_url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": raw.get("pdf_url") or f"https://arxiv.org/pdf/{arxiv_id}",
        "language": "en",
        "updated_at": raw.get("updated"),
    })
    return _finish(record)


def _crossref_year(raw: dict[str, Any]) -> tuple[int | None, str | None]:
    for key in ("published-print", "published-online", "issued", "created"):
        parts = ((raw.get(key) or {}).get("date-parts") or [[None]])[0]
        if parts and parts[0]:
            date = "-".join(f"{int(part):02d}" if index else str(part) for index, part in enumerate(parts) if part)
            return _year(parts[0]), date
    return None, None


def from_crossref(raw: dict[str, Any], fetched_at: str | None = None) -> dict[str, Any] | None:
    doi = normalize_doi(raw.get("DOI"))
    if not doi:
        return None
    record = _base("crossref", doi, fetched_at)
    year, date = _crossref_year(raw)
    pdf = next((link.get("URL") for link in raw.get("link") or [] if isinstance(link, dict) and "pdf" in str(link.get("content-type", ""))), None)
    authors = []
    for author in raw.get("author") or []:
        if not isinstance(author, dict):
            continue
        name = " ".join(part for part in [author.get("given"), author.get("family")] if part) or author.get("name")
        if name:
            authors.append({
                "name": strip_markup(name),
                "orcid": (author.get("ORCID") or "").rsplit("/", 1)[-1] or None,
                "affiliations": [aff.get("name") for aff in author.get("affiliation") or [] if isinstance(aff, dict) and aff.get("name")],
            })
    titles = raw.get("title") or []
    venues = raw.get("container-title") or []
    record.update({
        "doi": doi,
        "title": titles[0] if titles else "",
        "abstract": raw.get("abstract") or "",
        "year": year,
        "publication_date": date,
        "venue": venues[0] if venues else raw.get("publisher"),
        "type": raw.get("type"),
        "authors": authors,
        "topics": _clean_topics(raw.get("subject") or []),
        "citation_count": _int(raw.get("is-referenced-by-count")),
        "reference_count": _int(raw.get("references-count") or raw.get("reference-count")),
        "is_open_access": any("creativecommons" in str((lic or {}).get("URL", "")) for lic in raw.get("license") or []),
        "oa_url": raw.get("URL"),
        "pdf_url": pdf,
        "language": raw.get("language"),
        "updated_at": (raw.get("indexed") or {}).get("date-time"),
    })
    return _finish(record)


def from_semantic_scholar(raw: dict[str, Any], fetched_at: str | None = None) -> dict[str, Any] | None:
    source_id = raw.get("paperId")
    if not source_id:
        return None
    record = _base("semantic_scholar", str(source_id), fetched_at)
    external = raw.get("externalIds") if isinstance(raw.get("externalIds"), dict) else {}
    pdf = raw.get("openAccessPdf") if isinstance(raw.get("openAccessPdf"), dict) else {}
    venue = raw.get("venue") or ((raw.get("publicationVenue") or {}).get("name") if isinstance(raw.get("publicationVenue"), dict) else None)
    record.update({
        "doi": normalize_doi(external.get("DOI")),
        "arxiv_id": normalize_arxiv_id(external.get("ArXiv")) if external.get("ArXiv") else None,
        "title": raw.get("title") or "",
        "abstract": raw.get("abstract") or "",
        "year": _year(raw.get("year")),
        "publication_date": raw.get("publicationDate"),
        "venue": venue or None,
        "type": (raw.get("publicationTypes") or [None])[0],
        "authors": [{"name": strip_markup(a.get("name")), "orcid": None, "affiliations": []} for a in raw.get("authors") or [] if isinstance(a, dict) and a.get("name")],
        "topics": _clean_topics([*(raw.get("fieldsOfStudy") or []), *(raw.get("s2FieldsOfStudy") or [])]),
        "citation_count": _int(raw.get("citationCount")),
        "reference_count": _int(raw.get("referenceCount")),
        "is_open_access": bool(raw.get("isOpenAccess")),
        "oa_url": raw.get("url"),
        "pdf_url": pdf.get("url"),
    })
    return _finish(record)


NORMALIZERS = {
    "openalex": from_openalex,
    "arxiv": from_arxiv,
    "crossref": from_crossref,
    "semantic_scholar": from_semantic_scholar,
}


def normalize_envelope(envelope: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize one raw envelope; unknown sources and malformed records return None (never raise)."""
    normalizer = NORMALIZERS.get(str(envelope.get("source")))
    raw = envelope.get("raw")
    if normalizer is None or not isinstance(raw, dict):
        return None
    try:
        return normalizer(raw, envelope.get("fetched_at"))
    except Exception:  # noqa: BLE001 - a single malformed record must never stop a batch
        return None
