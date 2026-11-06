import httpx

from app.core.config import settings
from app.schemas.paper import PaperRecord
from app.schemas.search import SourceSearchRequest
from app.services.search.http_utils import get_json_with_backoff


class CrossrefProvider:
    source_name = "crossref"

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        async with httpx.AsyncClient(timeout=15) as client:
            payload = await get_json_with_backoff(
                client,
                f"{settings.crossref_base_url}/works",
                params={"query.bibliographic": request.query, "rows": request.limit, "mailto": settings.api_contact_email},
            )
        papers: list[PaperRecord] = []
        for item in payload.get("message", {}).get("items", []):
            papers.append(
                PaperRecord(
                    paper_id=item.get("DOI", f"crossref:{len(papers)}"),
                    title=(item.get("title") or ["Untitled"])[0],
                    abstract=item.get("abstract"),
                    year=((item.get("published-print") or item.get("created") or {}).get("date-parts", [[None]])[0][0]),
                    venue=(item.get("container-title") or [None])[0],
                    publication_type=item.get("type"),
                    doi=item.get("DOI"),
                    url=item.get("URL"),
                    citation_count=item.get("is-referenced-by-count", 0),
                    authors=[
                        {"name": " ".join(filter(None, [author.get("given"), author.get("family")])).strip()}
                        for author in item.get("author", [])
                    ],
                    source=self.source_name,
                    external_ids={"DOI": item.get("DOI", "")},
                )
            )
        return papers
