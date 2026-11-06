from __future__ import annotations

import html
import re
from urllib.parse import quote

import httpx

from app.schemas.paper import PaperRecord
from app.schemas.search import SourceSearchRequest
from app.services.search.http_utils import get_json_with_backoff


def _title(value: object) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))).strip()


class EuropePMCProvider:
    source_name = "europe_pmc"

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        async with httpx.AsyncClient(timeout=18) as client:
            payload = await get_json_with_backoff(client, "https://www.ebi.ac.uk/europepmc/webservices/rest/search", params={"query": request.query, "format": "json", "pageSize": request.limit, "resultType": "core"})
        return [self._paper(item, index) for index, item in enumerate(payload.get("resultList", {}).get("result", [])) if _title(item.get("title"))]

    def _paper(self, item: dict, index: int) -> PaperRecord:
        authors = [{"name": author.get("fullName")} for author in (item.get("authorList", {}).get("author") or []) if author.get("fullName")]
        doi = item.get("doi")
        paper_id = str(item.get("id") or item.get("pmid") or f"europepmc:{index}")
        fulltext_urls = item.get("fullTextUrlList", {}).get("fullTextUrl", []) or []
        pdf = next((entry.get("url") for entry in fulltext_urls if entry.get("documentStyle") == "pdf"), None)
        return PaperRecord(paper_id=paper_id, title=_title(item.get("title")), abstract=item.get("abstractText"), year=_year(item.get("firstPublicationDate")), venue=item.get("journalTitle"), doi=doi, url=item.get(" pmcid") and f"https://europepmc.org/articles/{item['pmcid']}" or item.get("pmid") and f"https://pubmed.ncbi.nlm.nih.gov/{item['pmid']}/", pdf_url=pdf, pdf_urls=[pdf] if pdf else [], citation_count=int(item.get("citedByCount") or 0), authors=authors, is_open_access=bool(pdf or item.get("isOpenAccess")), source=self.source_name)


class DoajProvider:
    source_name = "doaj"

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        async with httpx.AsyncClient(timeout=18) as client:
            payload = await get_json_with_backoff(client, f"https://doaj.org/api/search/articles/{quote(request.query)}", params={"pageSize": request.limit})
        papers = []
        for index, item in enumerate(payload.get("results", [])):
            bib = item.get("bibjson", {})
            title = _title(bib.get("title"))
            if not title:
                continue
            authors = [{"name": author.get("name")} for author in bib.get("author", []) if author.get("name")]
            links = [link.get("url") for link in bib.get("link", []) if link.get("url")]
            doi = next((identifier.get("id") for identifier in bib.get("identifier", []) if identifier.get("type") == "doi"), None)
            papers.append(PaperRecord(paper_id=doi or f"doaj:{item.get('id', index)}", title=title, abstract=bib.get("abstract"), year=_year(bib.get("year")), venue=bib.get("journal", {}).get("title"), doi=doi, url=links[0] if links else None, pdf_url=links[0] if links else None, is_open_access=True, authors=authors, source=self.source_name))
        return papers


class DblpProvider:
    source_name = "dblp"

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        async with httpx.AsyncClient(timeout=18) as client:
            payload = await get_json_with_backoff(client, "https://dblp.org/search/publ/api", params={"q": request.query, "format": "json", "h": request.limit}, headers={"Accept": "application/json"})
        hits = payload.get("result", {}).get("hits", {}).get("hit", [])
        papers = []
        for index, hit in enumerate(hits if isinstance(hits, list) else [hits]):
            info = hit.get("info", {})
            title = _title(info.get("title"))
            if not title:
                continue
            raw_authors = info.get("authors", {}).get("author", [])
            raw_authors = raw_authors if isinstance(raw_authors, list) else [raw_authors]
            authors = [{"name": item.get("text")} if isinstance(item, dict) else {"name": str(item)} for item in raw_authors if item]
            doi = info.get("doi")
            papers.append(PaperRecord(paper_id=doi or info.get("key") or f"dblp:{index}", title=title, year=_year(info.get("year")), venue=info.get("venue"), doi=doi, url=info.get("url"), authors=authors, source=self.source_name))
        return papers


class ZenodoProvider:
    source_name = "zenodo"

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        async with httpx.AsyncClient(timeout=18) as client:
            payload = await get_json_with_backoff(client, "https://zenodo.org/api/records", params={"q": request.query, "size": request.limit})
        papers = []
        for index, item in enumerate(payload.get("hits", {}).get("hits", [])):
            meta = item.get("metadata", {})
            title = _title(meta.get("title"))
            if not title:
                continue
            authors = [{"name": person.get("name")} for person in meta.get("creators", []) if person.get("name")]
            doi = meta.get("doi")
            pdf = next((link.get("url") for link in item.get("files", []) if link.get("type") == "pdf" or str(link.get("key", "")).lower().endswith(".pdf")), None)
            papers.append(PaperRecord(paper_id=doi or item.get("id") or f"zenodo:{index}", title=title, abstract=meta.get("description"), year=_year(meta.get("publication_date")), venue=meta.get("publisher"), doi=doi, url=item.get("links", {}).get("html"), pdf_url=pdf, is_open_access=True, authors=authors, source=self.source_name))
        return papers


class PreprintProvider(EuropePMCProvider):
    """bioRxiv/medRxiv preprints indexed by Europe PMC's official REST API."""

    source_name = "preprints"

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        async with httpx.AsyncClient(timeout=18) as client:
            payload = await get_json_with_backoff(client, "https://www.ebi.ac.uk/europepmc/webservices/rest/search", params={"query": f"({request.query}) AND SRC:PPR", "format": "json", "pageSize": request.limit, "resultType": "core"})
        return [self._paper(item, index).model_copy(update={"source": self.source_name}) for index, item in enumerate(payload.get("resultList", {}).get("result", [])) if _title(item.get("title"))]


class HalProvider:
    source_name = "hal"

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        async with httpx.AsyncClient(timeout=18) as client:
            payload = await get_json_with_backoff(client, "https://api.archives-ouvertes.fr/search/", params={"q": request.query, "wt": "json", "rows": request.limit, "fl": "docid,title_s,abstract_s,producedDateY_i,authFullName_s,uri_s,doiId_s"})
        papers = []
        for index, item in enumerate(payload.get("response", {}).get("docs", [])):
            title = _title(item.get("title_s"))
            if not title:
                continue
            raw_authors = item.get("authFullName_s", [])
            authors = [{"name": name} for name in (raw_authors if isinstance(raw_authors, list) else [raw_authors]) if name]
            doi = item.get("doiId_s")
            papers.append(PaperRecord(paper_id=doi or str(item.get("docid") or f"hal:{index}"), title=title, abstract=item.get("abstract_s"), year=_year(item.get("producedDateY_i")), doi=doi, url=item.get("uri_s"), authors=authors, source=self.source_name))
        return papers


def _year(value: object) -> int | None:
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None
