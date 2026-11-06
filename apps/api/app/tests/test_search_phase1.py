import asyncio

from app.schemas.paper import PaperRecord
from app.schemas.search import SearchFilters, SourceSearchRequest
from app.services.search.openalex_service import OpenAlexProvider
from app.services.search.service import FederatedSearchService
from app.services.storage.background_cache import BackgroundPaperCache


def make_paper(**overrides) -> PaperRecord:
    data = {
        "paper_id": "paper-1",
        "title": "Hybrid Retrieval for Academic Search",
        "abstract": "A paper about academic retrieval and search quality.",
        "citation_count": 10,
        "source": "openalex",
        "authors": [{"name": "A. Researcher"}],
    }
    data.update(overrides)
    return PaperRecord(**data)


def test_abstract_is_cleaned_on_paper_ingest() -> None:
    paper = make_paper(
        title="Machine learning and deep learning",
        abstract="<jats:p>Machine learning and deep learning: Abstract&nbsp; Today, &amp; tomorrow.</jats:p>",
    )

    assert paper.abstract == "Today, & tomorrow."


def test_abstract_prefix_cleaner_handles_summary_label_and_tags() -> None:
    paper = make_paper(abstract="<p>SUMMARY:  A &lt;useful&gt;   finding.</p>")

    assert paper.abstract == "A finding."


class SuccessfulProvider:
    source_name = "openalex"

    def __init__(self) -> None:
        self.last_request: SourceSearchRequest | None = None

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        self.last_request = request
        return [make_paper()]


class FailingProvider:
    source_name = "crossref"

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        raise RuntimeError("upstream timeout")


class RecordingCache(BackgroundPaperCache):
    def __init__(self) -> None:
        super().__init__()
        self.cached_batches: list[list[PaperRecord]] = []

    async def cache_search_results(self, papers: list[PaperRecord]):
        self.cached_batches.append(list(papers))
        return await super().cache_search_results(papers)


class EmptyWebSearch:
    async def search(self, query: str, limit: int = 10) -> list[PaperRecord]:
        return []


def test_federated_search_passes_structured_request_and_names_failures() -> None:
    success = SuccessfulProvider()
    failure = FailingProvider()
    cache = RecordingCache()
    service = FederatedSearchService(
        providers={
        success.source_name: success,
        failure.source_name: failure,
        },
        cache=cache,
        web_search=EmptyWebSearch(),
    )

    response = asyncio.run(
        service.search(
            "hybrid retrieval",
            5,
            [success.source_name, failure.source_name],
            page=1,
            language="ur",
            min_citations=5,
            open_access_only=False,
            study_type=None,
            quartile=None,
            sample_size_min=None,
        )
    )

    assert success.last_request is not None
    assert success.last_request.query
    assert success.last_request.page == 1
    assert success.last_request.filters.language == "ur"
    assert response.deduplicated_results == 1
    assert response.pagination.page == 1
    assert response.pagination.returned_results == 1
    assert response.source_failures == ["A research source is temporarily unavailable."]
    # Cache insertion is deliberately backgrounded; assert its eventual result below.
    assert len(cache.cached_batches) == 1


def test_federated_search_paginates_ranked_results() -> None:
    class BulkProvider:
        source_name = "openalex"

        async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
            return [
                PaperRecord(
                    paper_id="paper-0",
                    title="Hybrid Retrieval Benchmarks for Academic QA",
                    abstract="Benchmarks for academic question answering with retrieval pipelines.",
                    doi="10.1000/paper-0",
                    url="https://example.com/paper-0",
                    external_ids={"DOI": "10.1000/paper-0"},
                    citation_count=100,
                    authors=[{"name": "Alice"}],
                    source="openalex",
                ),
                PaperRecord(
                    paper_id="paper-1",
                    title="Cross-Lingual Evidence Ranking for Urdu Research Search",
                    abstract="Ranking multilingual evidence for Urdu and English research search.",
                    doi="10.1000/paper-1",
                    url="https://example.com/paper-1",
                    external_ids={"DOI": "10.1000/paper-1"},
                    citation_count=99,
                    authors=[{"name": "Bilal"}],
                    source="openalex",
                ),
                PaperRecord(
                    paper_id="paper-2",
                    title="Dataset Provenance Tracking in Scientific Workspaces",
                    abstract="Tracking provenance and dataset reuse inside scientific workspaces.",
                    doi="10.1000/paper-2",
                    url="https://example.com/paper-2",
                    external_ids={"DOI": "10.1000/paper-2"},
                    citation_count=98,
                    authors=[{"name": "Chris"}],
                    source="openalex",
                ),
                PaperRecord(
                    paper_id="paper-3",
                    title="Figure Grounding for Multimodal Literature Assistants",
                    abstract="Grounding figure-based answers in multimodal literature assistants.",
                    doi="10.1000/paper-3",
                    url="https://example.com/paper-3",
                    external_ids={"DOI": "10.1000/paper-3"},
                    citation_count=97,
                    authors=[{"name": "Dua"}],
                    source="openalex",
                ),
                PaperRecord(
                    paper_id="paper-4",
                    title="Citation Graph Drift Detection Across Research Trends",
                    abstract="Detecting drift in citation graphs across evolving research trends.",
                    doi="10.1000/paper-4",
                    url="https://example.com/paper-4",
                    external_ids={"DOI": "10.1000/paper-4"},
                    citation_count=96,
                    authors=[{"name": "Eman"}],
                    source="openalex",
                ),
            ]

    service = FederatedSearchService(providers={"openalex": BulkProvider()}, cache=RecordingCache(), web_search=EmptyWebSearch())

    response = asyncio.run(
        service.search(
            "hybrid retrieval",
            2,
            ["openalex"],
            page=2,
            language="en",
            min_citations=0,
            open_access_only=False,
            study_type=None,
            quartile=None,
            sample_size_min=None,
        )
    )

    assert response.deduplicated_results == 5
    assert response.pagination.page == 2
    assert response.pagination.total_pages == 3
    assert response.pagination.has_next_page is True
    assert len(response.papers) == 2


def test_plain_author_name_query_filters_to_author_list_matches() -> None:
    class AuthorProvider:
        source_name = "openalex"

        async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
            return [
                PaperRecord(
                    paper_id="author-match",
                    title="Learning Deep Architectures for AI",
                    abstract="Deep learning representation methods.",
                    citation_count=200,
                    authors=[{"name": "Y. Bengio"}],
                    source="openalex",
                ),
                PaperRecord(
                    paper_id="title-only-mention",
                    title="Ian Goodfellow, Yoshua Bengio, and Aaron Courville: Deep learning",
                    abstract="A book review mentioning Yoshua Bengio in the title.",
                    citation_count=150,
                    authors=[{"name": "Jeff Heaton"}],
                    source="openalex",
                ),
            ]

    service = FederatedSearchService(providers={"openalex": AuthorProvider()}, cache=RecordingCache(), web_search=EmptyWebSearch())

    response = asyncio.run(
        service.search(
            "Yoshua Bengio",
            5,
            ["openalex"],
            page=1,
            language="en",
            min_citations=0,
            open_access_only=False,
            study_type=None,
            quartile=None,
            sample_size_min=None,
        )
    )

    assert response.search_insights["author_intent"] == "Yoshua Bengio"
    assert [paper.paper_id for paper in response.papers] == ["author-match"]


def test_author_marker_query_keeps_topic_and_author_relevance() -> None:
    class AuthorTopicProvider:
        source_name = "openalex"

        async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
            return [
                PaperRecord(
                    paper_id="hinton-neural",
                    title="Reducing the Dimensionality of Data with Neural Networks",
                    abstract="A neural network paper.",
                    citation_count=300,
                    authors=[{"name": "Geoffrey E. Hinton"}],
                    source="openalex",
                ),
                PaperRecord(
                    paper_id="not-hinton",
                    title="Neural Network Survey",
                    abstract="Neural networks without the requested author.",
                    citation_count=250,
                    authors=[{"name": "Other Author"}],
                    source="openalex",
                ),
            ]

    service = FederatedSearchService(providers={"openalex": AuthorTopicProvider()}, cache=RecordingCache(), web_search=EmptyWebSearch())

    response = asyncio.run(
        service.search(
            "author Geoffrey Hinton neural networks",
            5,
            ["openalex"],
            page=1,
            language="en",
            min_citations=0,
            open_access_only=False,
            study_type=None,
            quartile=None,
            sample_size_min=None,
        )
    )

    assert response.search_insights["author_intent"] == "Geoffrey Hinton"
    assert [paper.paper_id for paper in response.papers] == ["hinton-neural"]


def test_multilingual_topic_query_is_translated_before_provider_search() -> None:
    class MultilingualProvider:
        source_name = "openalex"

        def __init__(self) -> None:
            self.last_request: SourceSearchRequest | None = None

        async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
            self.last_request = request
            if "artificial intelligence" not in request.query:
                return []
            return [
                PaperRecord(
                    paper_id="ai-paper",
                    title="Artificial Intelligence for Scientific Discovery",
                    abstract="A survey of artificial intelligence systems for research workflows.",
                    citation_count=220,
                    authors=[{"name": "A. Researcher"}],
                    source="openalex",
                )
            ]

    provider = MultilingualProvider()
    service = FederatedSearchService(providers={"openalex": provider}, cache=RecordingCache(), web_search=EmptyWebSearch())

    response = asyncio.run(
        service.search(
            "\u4eba\u5de5\u667a\u80fd",
            5,
            ["openalex"],
            page=1,
            language="en",
            min_citations=0,
            open_access_only=False,
            study_type=None,
            quartile=None,
            sample_size_min=None,
        )
    )

    assert provider.last_request is not None
    assert provider.last_request.query == "artificial intelligence"
    assert response.normalized_query == "artificial intelligence"
    assert response.translated_query == "artificial intelligence"
    assert [paper.paper_id for paper in response.papers] == ["ai-paper"]


def test_multilingual_author_marker_keeps_author_and_topic_relevance() -> None:
    class AuthorTopicProvider:
        source_name = "openalex"

        def __init__(self) -> None:
            self.requests: list[SourceSearchRequest] = []

        async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
            self.requests.append(request)
            return [
                PaperRecord(
                    paper_id="hinton-neural",
                    title="Neural Networks for Representation Learning",
                    abstract="Neural network methods from the requested author.",
                    citation_count=180,
                    authors=[{"name": "Geoffrey Hinton"}],
                    source="openalex",
                ),
                PaperRecord(
                    paper_id="other-neural",
                    title="Neural Network Methods",
                    abstract="Neural network methods from another author.",
                    citation_count=190,
                    authors=[{"name": "Other Author"}],
                    source="openalex",
                ),
            ]

    provider = AuthorTopicProvider()
    service = FederatedSearchService(providers={"openalex": provider}, cache=RecordingCache(), web_search=EmptyWebSearch())

    response = asyncio.run(
        service.search(
            "\u4f5c\u8005 Geoffrey Hinton \u795e\u7ecf\u7f51\u7edc",
            5,
            ["openalex"],
            page=1,
            language="en",
            min_citations=0,
            open_access_only=False,
            study_type=None,
            quartile=None,
            sample_size_min=None,
        )
    )

    assert provider.requests
    assert provider.requests[0].query == "neural networks Geoffrey Hinton"
    assert response.search_insights["author_intent"] == "Geoffrey Hinton"
    assert [paper.paper_id for paper in response.papers] == ["hinton-neural"]


def test_openalex_provider_handles_missing_primary_location_source_gracefully(monkeypatch) -> None:
    async def fake_get_json_with_backoff(client, url, *, params=None, headers=None, attempts=3, base_delay=0.4):
        return {
            "results": [
                {
                    "id": "https://openalex.org/W123",
                    "title": "Deepfake Video Detection Using Recurrent Neural Networks",
                    "display_name": "Deepfake Video Detection Using Recurrent Neural Networks",
                    "publication_year": 2018,
                    "primary_location": {"source": None, "pdf_url": None},
                    "doi": "https://doi.org/10.1109/avss.2018.8639163",
                    "cited_by_count": 42,
                    "referenced_works_count": 18,
                    "open_access": {"is_oa": True},
                    "authorships": [{"author": {"display_name": "A. Researcher"}}],
                    "ids": {"doi": "https://doi.org/10.1109/avss.2018.8639163"},
                }
            ]
        }

    monkeypatch.setattr("app.services.search.openalex_service.get_json_with_backoff", fake_get_json_with_backoff)

    request = SourceSearchRequest(query="deepfake detection", limit=3, filters=SearchFilters())
    papers = asyncio.run(OpenAlexProvider().search(request))

    assert len(papers) == 1
    assert papers[0].title == "Deepfake Video Detection Using Recurrent Neural Networks"
    assert papers[0].venue is None
    assert papers[0].pdf_url is None
    assert papers[0].source == "openalex"


def test_federated_search_returns_empty_when_sources_return_nothing() -> None:
    class EmptyProvider:
        source_name = "openalex"

        async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
            return []

    service = FederatedSearchService(providers={"openalex": EmptyProvider()}, cache=RecordingCache(), web_search=EmptyWebSearch())

    response = asyncio.run(
        service.search(
            "hybrid retrieval benchmark",
            5,
            ["openalex"],
            page=1,
            language="en",
            min_citations=0,
            open_access_only=False,
            study_type=None,
            quartile=None,
            sample_size_min=None,
        )
    )

    assert response.deduplicated_results == 0
    assert response.papers == []
    assert response.trending_topics == []


def test_federated_search_does_not_top_up_sparse_live_results_with_unrelated_fallback() -> None:
    class SparseProvider:
        source_name = "openalex"

        async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
            return [
                PaperRecord(
                    paper_id="brfss-diabetes",
                    title="Diabetes Prediction Using the BRFSS Dataset",
                    abstract="Machine learning models for diabetes prediction using BRFSS survey data.",
                    citation_count=12,
                    authors=[{"name": "A. Researcher"}],
                    source="openalex",
                )
            ]

    service = FederatedSearchService(providers={"openalex": SparseProvider()}, cache=RecordingCache(), web_search=EmptyWebSearch())

    response = asyncio.run(
        service.search(
            "diabetes prediction using brfss dataset",
            10,
            ["openalex", "semantic_scholar", "crossref", "arxiv", "pubmed", "core"],
            page=1,
            language="en",
            min_citations=0,
            open_access_only=False,
            study_type=None,
            quartile=None,
            sample_size_min=None,
        )
    )

    assert [paper.paper_id for paper in response.papers] == ["brfss-diabetes"]


def test_unmapped_chinese_query_uses_fake_translation_before_search(monkeypatch) -> None:
    from app.services.search import service as search_service_module

    class CapturingProvider:
        source_name = "openalex"

        def __init__(self):
            self.requests = []

        async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
            self.requests.append(request)
            return [make_paper()]

    provider = CapturingProvider()
    calls = []

    def fake_translate(text, target, **kwargs):
        calls.append((text, target, kwargs.get("source_language")))
        return "graph neural networks for medicine"

    monkeypatch.setattr(search_service_module, "translate_text", fake_translate)
    service = FederatedSearchService(providers={"openalex": provider}, cache=RecordingCache(), web_search=EmptyWebSearch())
    response = asyncio.run(service.search(
        "\u590d\u6742\u7684\u533b\u7597\u56fe\u795e\u7ecf\u7f51\u7edc\u7814\u7a76", 5, ["openalex"], page=1, query_language="auto",
        language="en", save_history=False,
    ))

    assert calls == [("\u590d\u6742\u7684\u533b\u7597\u56fe\u795e\u7ecf\u7f51\u7edc\u7814\u7a76", "en", "zh-Hans")]
    assert any(request.query == "graph neural networks for medicine" for request in provider.requests)
    assert response.translated_query == "graph neural networks for medicine"


def test_requested_results_language_translates_titles_before_response(monkeypatch) -> None:
    from app.services.search import service as search_service_module

    provider = SuccessfulProvider()
    monkeypatch.setattr(search_service_module, "translate_batch", lambda segments, target, user_id=None, user_content=False: [f"translated: {segment}" for segment in segments])
    service = FederatedSearchService(providers={"openalex": provider}, cache=RecordingCache(), web_search=EmptyWebSearch())
    response = asyncio.run(service.search(
        "hybrid retrieval", 5, ["openalex"], page=1, language="zh-Hans",
        target_language="zh-Hans", translate_results=True, save_history=False,
    ))

    assert response.papers[0].translated_title == "translated: Hybrid Retrieval for Academic Search"
    assert response.papers[0].translated_abstract.startswith("translated: ")
    assert response.papers[0].translation_status == "translated"

