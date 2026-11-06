import asyncio

from app.schemas.paper import PaperRecord
from app.services.search.web_search import WebSearchService, _result_paper


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.counts = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value

    async def eval(self, script, key_count, key, cost, maximum, ttl):
        used = self.counts.get(key, 0)
        if used + int(cost) > int(maximum):
            return 0
        self.counts[key] = used + int(cost)
        return 1


class FakeProvider:
    def __init__(self, name, result=None, error=None, budget=1000):
        self.name = name
        self.result = result or []
        self.error = error
        self.monthly_credit_limit = budget
        self.credit_cost = 1
        self.calls = 0

    async def search(self, query, limit):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result[:limit]


def web_item(index=1):
    return PaperRecord(
        paper_id=f"web:{index}",
        title="Machine learning in healthcare",
        abstract="Clean web snippet.",
        venue="example.org",
        publication_type="web",
        url="https://www.example.org/article",
        source="web",
        authors=[],
        result_badges=["Web"],
    )


def test_provider_fallback_and_query_cache_use_fake_providers_only():
    async def run():
        redis = FakeRedis()
        primary = FakeProvider("tavily", error=RuntimeError("offline"))
        fallback = FakeProvider("exa", [web_item()])
        service = WebSearchService([primary, fallback], redis)
        first = await service.search("Machine learning in healthcare", 10)
        second = await service.search(" machine learning   in healthcare ", 10)
        assert len(first) == len(second) == 1
        assert primary.calls == fallback.calls == 1
        assert first[0].source == "web"
        assert "provider" not in first[0].external_ids

    asyncio.run(run())


def test_missing_keys_skip_all_web_providers(monkeypatch):
    monkeypatch.setattr("app.services.search.web_search.settings.tavily_api_key", None)
    monkeypatch.setattr("app.services.search.web_search.settings.exa_api_key", None)
    service = WebSearchService(redis_client=FakeRedis())
    assert service.providers == []
    assert asyncio.run(service.search("machine learning in healthcare")) == []


def test_tavily_web_result_parser_keeps_site_not_provider_identity():
    paper = _result_paper("tavily", {
        "title": "Research result",
        "url": "https://www.example.org/path",
        "content": ["Useful", "snippet"],
        "published_date": "2024-05-14",
    }, 0)
    assert paper is not None
    assert paper.publication_type == "web"
    assert paper.source == "web"
    assert paper.venue == "www.example.org"
    assert paper.year == 2024
    assert paper.abstract == "Useful snippet"
    assert "provider" not in paper.external_ids


def test_federated_search_mixes_fake_web_and_scholarly_results():
    from app.services.search.service import FederatedSearchService
    from app.schemas.search import SourceSearchRequest

    class FakePaperProvider:
        source_name = "openalex"

        async def search(self, request: SourceSearchRequest):
            return [web_item("paper").model_copy(update={
                "paper_id": "paper:1",
                "publication_type": "article",
                "source": "openalex",
                "venue": "Medical AI Journal",
                "result_badges": [],
            })]

    class FakeWebProvider:
        async def search(self, query, limit=10):
            return [web_item("web").model_copy(update={"title": "Machine learning for better hospitals"})]

    async def run():
        service = FederatedSearchService(
            providers={"openalex": FakePaperProvider()},
            web_search=FakeWebProvider(),
        )
        return await service.search("machine learning healthcare", 10, ["openalex"])

    response = asyncio.run(run())
    assert any(paper.publication_type == "web" for paper in response.papers)
    assert any(paper.publication_type != "web" for paper in response.papers)


def test_federated_search_emits_incremental_source_events_with_fake_providers():
    from app.services.search.service import FederatedSearchService
    from app.schemas.search import SourceSearchRequest

    class FakePaperProvider:
        source_name = "openalex"

        async def search(self, request: SourceSearchRequest):
            return [web_item("stream-paper").model_copy(update={
                "paper_id": "stream-paper",
                "publication_type": "article",
                "source": "openalex",
                "venue": "Research Journal",
            })]

    class FakeWebProvider:
        async def search(self, query, limit=10):
            return [web_item("stream-web").model_copy(update={"paper_id": "stream-web"})]

    async def run():
        events = []
        service = FederatedSearchService(
            providers={"openalex": FakePaperProvider()},
            web_search=FakeWebProvider(),
        )
        response = await service.search(
            "machine learning healthcare", 10, ["openalex"], save_history=False,
            source_event_callback=lambda event, payload: events.append((event, payload)),
        )
        return response, events

    response, events = asyncio.run(run())
    assert {event for event, _payload in events} >= {"source_started", "source_results"}
    assert all("source" not in payload for event, payload in events)
    partial_batches = [payload["papers"] for event, payload in events if event == "source_results"]
    assert {paper["paper_id"] for batch in partial_batches for paper in batch} == {"stream-paper", "stream-web"}
    assert {paper.paper_id for paper in response.papers} == {"stream-paper"}


def test_search_stream_endpoint_emits_partial_results_and_final_response(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.schemas.paper import PaperSearchResponse, SearchPagination
    from app.api.v1.endpoints import search as search_endpoint

    result = web_item("sse-fixture").model_copy(update={"publication_type": "article", "source": "fixture"})

    class FakeSearchService:
        async def search(self, query, limit, sources, **kwargs):
            callback = kwargs["source_event_callback"]
            callback("source_started", {"source": "fixture"})
            callback("source_results", {"source": "fixture", "papers": [result.model_dump(mode="json")]})
            return PaperSearchResponse(
                query=query,
                normalized_query=query,
                total_results=1,
                deduplicated_results=1,
                papers=[result],
                pagination=SearchPagination(page=1, page_size=limit, returned_results=1, total_pages=1, has_next_page=False),
            )

    monkeypatch.setattr(search_endpoint, "service", FakeSearchService())
    with TestClient(app) as client:
        response = client.post("/api/v1/search/stream", json={"query": "streaming research", "sources": ["openalex"]})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: source_started" not in response.text  # Internal connector lifecycle stays private.
    assert "event: source_results" in response.text
    assert "sse-fixture" in response.text
    assert '"source": "fixture"' not in response.text
    assert '"source":"fixture"' not in response.text
    assert '"source":"research"' in response.text
    assert '"source":"openalex"' not in response.text
    assert "event: done" in response.text
    assert response.text.index("event: source_results") < response.text.index("event: done")
