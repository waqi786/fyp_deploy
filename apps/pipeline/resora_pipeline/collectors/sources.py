"""Collectors for OpenAlex, arXiv, Crossref and Semantic Scholar.

Each uses the provider's recommended bulk/cursor API and documented polite limits:
  * OpenAlex  /works  cursor pagination, `mailto` polite pool, filter from_updated_date (incremental), ≤10 req/s.
  * arXiv     export API (Atom), start/max_results paging, ≥3 s between calls as the API terms ask.
  * Crossref  /works cursor=*, `mailto` polite pool, filter from-update-date, 1 req/s here to stay friendly.
  * Semantic Scholar  /graph/v1/paper/search/bulk with continuation tokens; API key optional (raises the limit).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterator
from typing import Any

from resora_pipeline.collectors.base import Collector

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"


class OpenAlexCollector(Collector):
    source = "openalex"
    rate_per_second = 8.0
    page_size = 200
    base_url = "https://api.openalex.org/works"

    def pages(self, query: str, *, since: str | None, max_records: int) -> Iterator[dict[str, Any]]:
        cursor = "*"
        fetched = 0
        filters = [f"from_updated_date:{since}"] if since else []
        while cursor and fetched < max_records:
            params: dict[str, Any] = {"search": query, "per-page": min(self.page_size, max_records - fetched), "cursor": cursor, "mailto": self.config.contact_email}
            if filters:
                params["filter"] = ",".join(filters)
            payload = self.get(self.base_url, params=params).json()
            results = payload.get("results") or []
            for item in results:
                fetched += 1
                yield item
            cursor = (payload.get("meta") or {}).get("next_cursor") if results else None


class ArxivCollector(Collector):
    source = "arxiv"
    rate_per_second = 1 / 3  # arXiv asks for at most one request every three seconds
    page_size = 100
    base_url = "http://export.arxiv.org/api/query"

    @staticmethod
    def parse_feed(xml_text: str) -> list[dict[str, Any]]:
        root = ET.fromstring(xml_text)
        entries = []
        for entry in root.findall(f"{ATOM}entry"):
            def text(tag: str, ns: str = ATOM) -> str:
                node = entry.find(f"{ns}{tag}")
                return " ".join((node.text or "").split()) if node is not None else ""

            pdf = next((link.get("href") for link in entry.findall(f"{ATOM}link") if link.get("title") == "pdf"), None)
            entries.append({
                "id": text("id"),
                "title": text("title"),
                "summary": text("summary"),
                "published": text("published"),
                "updated": text("updated"),
                "doi": text("doi", ARXIV) or None,
                "journal_ref": text("journal_ref", ARXIV) or None,
                "primary_category": (entry.find(f"{ARXIV}primary_category").get("term") if entry.find(f"{ARXIV}primary_category") is not None else None),
                "categories": [node.get("term") for node in entry.findall(f"{ATOM}category") if node.get("term")],
                "authors": [
                    {"name": " ".join((author.findtext(f"{ATOM}name") or "").split()), "affiliation": author.findtext(f"{ARXIV}affiliation")}
                    for author in entry.findall(f"{ATOM}author")
                ],
                "pdf_url": pdf,
            })
        return entries

    def pages(self, query: str, *, since: str | None, max_records: int) -> Iterator[dict[str, Any]]:
        start = 0
        search = query if ":" in query else f'all:"{query}"'
        if since:
            search = f"({search}) AND submittedDate:[{since.replace('-', '')}0000 TO 999912312359]"
        while start < max_records:
            params = {"search_query": search, "start": start, "max_results": min(self.page_size, max_records - start), "sortBy": "lastUpdatedDate", "sortOrder": "descending"}
            entries = self.parse_feed(self.get(self.base_url, params=params).text)
            if not entries:
                return
            yield from entries
            start += len(entries)


class CrossrefCollector(Collector):
    source = "crossref"
    rate_per_second = 1.0
    page_size = 100
    base_url = "https://api.crossref.org/works"

    def pages(self, query: str, *, since: str | None, max_records: int) -> Iterator[dict[str, Any]]:
        cursor = "*"
        fetched = 0
        while cursor and fetched < max_records:
            params: dict[str, Any] = {"query.bibliographic": query, "rows": min(self.page_size, max_records - fetched), "cursor": cursor, "mailto": self.config.contact_email}
            if since:
                params["filter"] = f"from-update-date:{since}"
            message = (self.get(self.base_url, params=params).json() or {}).get("message") or {}
            items = message.get("items") or []
            for item in items:
                fetched += 1
                yield item
            cursor = message.get("next-cursor") if items else None


class SemanticScholarCollector(Collector):
    source = "semantic_scholar"
    rate_per_second = 1.0
    page_size = 1000
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
    fields = "paperId,externalIds,title,abstract,year,publicationDate,venue,publicationVenue,publicationTypes,authors,fieldsOfStudy,s2FieldsOfStudy,citationCount,referenceCount,isOpenAccess,openAccessPdf,url"

    def pages(self, query: str, *, since: str | None, max_records: int) -> Iterator[dict[str, Any]]:
        token = None
        fetched = 0
        headers = {"x-api-key": self.config.semantic_scholar_api_key} if self.config.semantic_scholar_api_key else None
        while fetched < max_records:
            params: dict[str, Any] = {"query": query, "fields": self.fields}
            if since:
                params["publicationDateOrYear"] = f"{since}:"
            if token:
                params["token"] = token
            payload = self.get(self.base_url, params=params, headers=headers).json()
            data = payload.get("data") or []
            for item in data:
                fetched += 1
                yield item
                if fetched >= max_records:
                    return
            token = payload.get("token")
            if not data or not token:
                return


COLLECTORS: dict[str, type[Collector]] = {
    "openalex": OpenAlexCollector,
    "arxiv": ArxivCollector,
    "crossref": CrossrefCollector,
    "semantic_scholar": SemanticScholarCollector,
}
