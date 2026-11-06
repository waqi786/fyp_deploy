import httpx

from app.core.config import settings
from app.schemas.paper import PaperRecord
from app.schemas.search import SourceSearchRequest
from app.services.search.http_utils import get_json_with_backoff


class GoogleScholarProvider:
    source_name = "google_scholar"

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        if not settings.serpapi_api_key:
            return []
        async with httpx.AsyncClient(timeout=20) as client:
            payload = await get_json_with_backoff(
                client,
                "https://serpapi.com/search.json",
                params={
                    "engine": "google_scholar",
                    "q": request.query,
                    "num": min(request.limit, 20),
                    "api_key": settings.serpapi_api_key,
                },
            )
        papers: list[PaperRecord] = []
        for item in payload.get("organic_results", []):
            title = item.get("title")
            if not title:
                continue
            publication = item.get("publication_info") or {}
            authors = [{"name": author} for author in publication.get("authors", [])]
            pdf_url = None
            resources = item.get("resources") or []
            for resource in resources:
                link = resource.get("link")
                if link and link.endswith(".pdf"):
                    pdf_url = link
                    break
            papers.append(
                PaperRecord(
                    paper_id=item.get("result_id") or f"scholar:{len(papers)}",
                    title=title,
                    abstract=item.get("snippet"),
                    year=publication.get("year"),
                    venue=publication.get("summary"),
                    url=item.get("link"),
                    pdf_url=pdf_url,
                    citation_count=((item.get("inline_links") or {}).get("cited_by") or {}).get("total", 0),
                    authors=authors,
                    source=self.source_name,
                )
            )
        return papers
