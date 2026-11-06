import asyncio

from app.schemas.paper import PaperRecord
from app.schemas.search import SourceSearchRequest
from app.services.search.load_testing import SearchLoadTester
from app.services.search.service import FederatedSearchService
from app.services.storage.background_cache import BackgroundPaperCache


class FastProvider:
    source_name = "openalex"

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        return [
            PaperRecord(
                paper_id=f"paper-{request.query}",
                title="Fast Synthetic Search Result",
                abstract="Synthetic result used for concurrent search verification.",
                citation_count=12,
                source=self.source_name,
            )
        ]


class EmptyWebSearch:
    async def search(self, query: str, limit: int = 10) -> list[PaperRecord]:
        return []


def test_search_load_tester_handles_fifty_concurrent_users() -> None:
    service = FederatedSearchService(
        providers={"openalex": FastProvider()},
        cache=BackgroundPaperCache(),
        web_search=EmptyWebSearch(),
    )
    tester = SearchLoadTester(service)

    report = asyncio.run(
        tester.run(
            concurrent_users=50,
            query="hybrid retrieval",
            sources=["openalex"],
            limit=5,
        )
    )

    assert report.concurrent_users == 50
    assert report.requests_completed == 50
    assert report.average_latency_ms >= 0
