import httpx

from app.core.config import settings
from app.schemas.paper import PaperRecord
from app.schemas.search import SourceSearchRequest
from app.services.search.http_utils import get_text_with_backoff


class ArxivProvider:
    source_name = "arxiv"

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        content = await self._fetch_feed(request)
        papers: list[PaperRecord] = []
        entries = content.split("<entry>")[1:]
        for index, entry in enumerate(entries):
            title = _extract_tag(entry, "title") or "Untitled"
            summary = _extract_tag(entry, "summary")
            paper_id = _extract_tag(entry, "id") or f"arxiv:{index}"
            pdf_url = None
            for line in entry.splitlines():
                if 'title="pdf"' in line and 'href="' in line:
                    pdf_url = line.split('href="', 1)[1].split('"', 1)[0]
                    break
            papers.append(
                PaperRecord(
                    paper_id=paper_id,
                    title=" ".join(title.split()),
                    abstract=" ".join(summary.split()) if summary else None,
                    url=paper_id,
                    pdf_url=pdf_url,
                    pdf_urls=[pdf_url] if pdf_url else [],
                    is_open_access=bool(pdf_url),
                    source=self.source_name,
                )
            )
        return papers

    async def _fetch_feed(self, request: SourceSearchRequest) -> str:
        async with httpx.AsyncClient(timeout=15) as client:
            return await get_text_with_backoff(
                client,
                settings.arxiv_base_url,
                params={"search_query": f"all:{request.query}", "start": 0, "max_results": request.limit},
                headers={"User-Agent": "Resora/0.1"},
            )


def _extract_tag(entry: str, tag: str) -> str | None:
    opening = f"<{tag}>"
    closing = f"</{tag}>"
    if opening not in entry or closing not in entry:
        return None
    return entry.split(opening, 1)[1].split(closing, 1)[0].strip()
