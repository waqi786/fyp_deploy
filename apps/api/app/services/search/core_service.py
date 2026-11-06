import httpx

from app.core.config import settings
from app.schemas.paper import PaperRecord
from app.schemas.search import SourceSearchRequest
from app.services.search.http_utils import get_json_with_backoff


class CoreProvider:
    source_name = "core"

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        async with httpx.AsyncClient(timeout=20) as client:
            payload = await get_json_with_backoff(
                client,
                f"{settings.core_base_url}/search/works",
                params={"q": request.query, "limit": request.limit},
            )
        papers: list[PaperRecord] = []
        for item in payload.get("results", []):
            papers.append(
                PaperRecord(
                    paper_id=str(item.get("id") or f"core:{len(papers)}"),
                    title=item.get("title") or "Untitled",
                    abstract=item.get("abstract"),
                    year=item.get("yearPublished"),
                    venue=item.get("publisher"),
                    doi=item.get("doi"),
                    url=item.get("downloadUrl") or item.get("sourceFulltextUrls", [None])[0],
                    pdf_url=item.get("downloadUrl"),
                    citation_count=0,
                    reference_count=0,
                    is_open_access=bool(item.get("downloadUrl")),
                    authors=[{"name": author.get("name")} for author in item.get("authors", []) if author.get("name")],
                    source=self.source_name,
                    external_ids={"DOI": item.get("doi", "")},
                )
            )
        return papers
