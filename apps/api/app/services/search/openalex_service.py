import httpx

from app.core.config import settings
from app.schemas.paper import PaperRecord
from app.schemas.search import SourceSearchRequest
from app.services.search.http_utils import get_json_with_backoff


class OpenAlexProvider:
    source_name = "openalex"

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        params = {"search": request.query, "per-page": request.limit, "page": request.page, "mailto": settings.api_contact_email}
        async with httpx.AsyncClient(timeout=15) as client:
            payload = await get_json_with_backoff(client, f"{settings.openalex_base_url}/works", params=params)
        papers: list[PaperRecord] = []
        for item in payload.get("results", []):
            primary_location = item.get("primary_location") if isinstance(item.get("primary_location"), dict) else None
            source_info = primary_location.get("source") if isinstance(primary_location, dict) else None
            venue = source_info.get("display_name") if isinstance(source_info, dict) else None
            pdf_url = primary_location.get("pdf_url") if isinstance(primary_location, dict) else None
            pdf_urls = list(dict.fromkeys(
                location.get("pdf_url")
                for location in (item.get("locations") or [])
                if isinstance(location, dict) and isinstance(location.get("pdf_url"), str)
            ))
            authors = []
            for author in item.get("authorships", []):
                author_info = author.get("author") if isinstance(author, dict) else None
                if isinstance(author_info, dict) and author_info.get("display_name"):
                    authors.append({"name": author_info.get("display_name")})

            papers.append(
                PaperRecord(
                    paper_id=item.get("id") or item.get("doi") or f"openalex:{len(papers)}",
                    title=item.get("title") or item.get("display_name") or "Untitled",
                    abstract=item.get("abstract") or _abstract_from_inverted_index(item.get("abstract_inverted_index")),
                    year=item.get("publication_year"),
                    venue=venue,
                    publication_type=item.get("type"),
                    doi=item.get("doi"),
                    url=item.get("id"),
                    pdf_url=pdf_url,
                    pdf_urls=pdf_urls,
                    citation_count=item.get("cited_by_count", 0),
                    reference_count=item.get("referenced_works_count", 0),
                    is_open_access=(item.get("open_access") or {}).get("is_oa", False) if isinstance(item.get("open_access"), dict) else False,
                    authors=authors,
                    source=self.source_name,
                    external_ids=item.get("ids") or {},
                )
            )
        return papers


def _abstract_from_inverted_index(value: object) -> str | None:
    if not isinstance(value, dict) or not value:
        return None
    positioned: list[tuple[int, str]] = []
    for token, positions in value.items():
        if not isinstance(token, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int):
                positioned.append((position, token))
    if not positioned:
        return None
    return " ".join(token for _, token in sorted(positioned)).strip() or None
