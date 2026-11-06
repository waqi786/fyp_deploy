import httpx

from app.core.config import settings
from app.schemas.paper import PaperRecord
from app.schemas.search import SourceSearchRequest
from app.services.search.http_utils import get_json_with_backoff


class PMCProvider:
    source_name = "pmc"

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        async with httpx.AsyncClient(timeout=20) as client:
            search_payload = await get_json_with_backoff(
                client,
                f"{settings.pmc_base_url}/esearch.fcgi",
                params={"db": "pmc", "term": request.query, "retmax": request.limit, "retmode": "json"},
            )
        ids = search_payload.get("esearchresult", {}).get("idlist", [])
        return [
            PaperRecord(
                paper_id=f"pmc:{pmc_id}",
                title=f"PMC article {pmc_id}",
                abstract=None,
                url=f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmc_id}/",
                pdf_url=f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmc_id}/pdf/",
                is_open_access=True,
                source=self.source_name,
            )
            for pmc_id in ids
        ]
