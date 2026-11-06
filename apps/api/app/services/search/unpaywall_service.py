from urllib.parse import quote

import httpx

from app.core.config import settings
from app.schemas.paper import PaperRecord
from app.schemas.search import SourceSearchRequest
from app.services.search.http_utils import get_json_with_backoff


class UnpaywallProvider:
    source_name = "unpaywall"

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        normalized = quote(request.query.strip())
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                payload = await get_json_with_backoff(
                    client,
                    f"{settings.unpaywall_base_url}/{normalized}",
                    params={"email": settings.unpaywall_email},
                )
            except RuntimeError:
                return []
        title = payload.get("title")
        if not title:
            return []
        return [
            PaperRecord(
                paper_id=payload.get("doi", normalized),
                title=title,
                abstract=None,
                year=payload.get("year"),
                venue=payload.get("journal_name"),
                doi=payload.get("doi"),
                url=payload.get("doi_url"),
                pdf_url=((payload.get("best_oa_location") or {}).get("url_for_pdf")),
                is_open_access=payload.get("is_oa", False),
                source=self.source_name,
                external_ids={"DOI": payload.get("doi", "")},
            )
        ]
