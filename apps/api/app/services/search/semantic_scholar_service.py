import httpx

from app.core.config import settings
from app.schemas.paper import PaperRecord
from app.schemas.search import SourceSearchRequest
from app.services.search.http_utils import get_json_with_backoff


class SemanticScholarProvider:
    source_name = "semantic_scholar"

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        headers = {}
        if settings.semantic_scholar_api_key:
            headers["x-api-key"] = settings.semantic_scholar_api_key
        async with httpx.AsyncClient(timeout=20) as client:
            payload = await get_json_with_backoff(
                client,
                f"{settings.semantic_scholar_base_url}/paper/search",
                params={
                    "query": request.query,
                    "limit": request.limit,
                    "fields": "paperId,title,abstract,year,venue,citationCount,referenceCount,openAccessPdf,externalIds,authors,url",
                },
                headers=headers or None,
            )
        papers: list[PaperRecord] = []
        for item in payload.get("data", []):
            external_ids = {
                str(key): str(value)
                for key, value in (item.get("externalIds") or {}).items()
                if value is not None
            }
            papers.append(
                PaperRecord(
                    paper_id=item.get("paperId") or f"semanticscholar:{len(papers)}",
                    title=item.get("title") or "Untitled",
                    abstract=item.get("abstract"),
                    year=item.get("year"),
                    venue=item.get("venue"),
                    doi=(item.get("externalIds") or {}).get("DOI"),
                    url=item.get("url"),
                    pdf_url=((item.get("openAccessPdf") or {}).get("url")),
                    pdf_urls=[(item.get("openAccessPdf") or {}).get("url")] if (item.get("openAccessPdf") or {}).get("url") else [],
                    citation_count=item.get("citationCount", 0),
                    reference_count=item.get("referenceCount", 0),
                    is_open_access=bool((item.get("openAccessPdf") or {}).get("url")),
                    authors=[{"name": author.get("name")} for author in item.get("authors", []) if author.get("name")],
                    source=self.source_name,
                    external_ids=external_ids,
                )
            )
        return papers
