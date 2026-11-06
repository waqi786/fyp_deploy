from pathlib import Path

import pytest

from app.schemas.paper import PaperRecord
from app.schemas.search import SavedSearchRequest, SearchFilters
from app.services.search.workspace import SearchWorkspaceService


@pytest.fixture(autouse=True)
def isolated_workspace_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(SearchWorkspaceService, "_store_path", tmp_path / "search_workspace.json")
    SearchWorkspaceService._saved_searches = []
    SearchWorkspaceService._history = []
    SearchWorkspaceService._trending_papers = []
    SearchWorkspaceService._trending_topics = []
    SearchWorkspaceService._scopes = {}
    SearchWorkspaceService._loaded = False


def make_paper(**overrides) -> PaperRecord:
    data = {
        "paper_id": "paper-1",
        "title": "Resora Retrieval Benchmark Dataset",
        "abstract": "A benchmark dataset for academic retrieval.",
        "year": 2025,
        "venue": "Research Systems",
        "doi": "10.1000/resora",
        "url": "https://example.com/resora",
        "citation_count": 40,
        "is_open_access": True,
        "authors": [{"name": "Alice Researcher"}],
        "source": "openalex",
    }
    data.update(overrides)
    return PaperRecord(**data)


def test_workspace_tracks_saved_searches_history_and_trending() -> None:
    service = SearchWorkspaceService()
    saved = service.save_search(
        SavedSearchRequest(
            name="RAG Benchmarks",
            query="hybrid retrieval benchmark",
            sources=["openalex", "arxiv"],
            filters=SearchFilters(open_access_only=True),
            alert_enabled=True,
            alert_cadence="weekly",
        )
    )
    session_id = service.record_history(
        query="hybrid retrieval benchmark",
        normalized_query="hybrid retrieval benchmark",
        sources=["openalex", "arxiv"],
        result_count=3,
    )
    service.update_trending([make_paper(recommendation_reason="Trending in retrieval evaluation.")], ["Retrieval", "Benchmark"])

    snapshot = service.snapshot()
    trending = service.trending()

    assert saved.id.startswith("saved-")
    assert session_id.startswith("search-")
    assert snapshot.saved_searches
    assert snapshot.history
    assert snapshot.alert_previews
    assert snapshot.alert_previews[0].query == "hybrid retrieval benchmark"
    assert trending.topics == ["Retrieval", "Benchmark"]
    assert trending.papers[0].title == "Resora Retrieval Benchmark Dataset"


def test_workspace_persists_saved_searches_history_and_trending_across_service_reload() -> None:
    service = SearchWorkspaceService()
    service.save_search(
        SavedSearchRequest(
            name="Persistent Alerts",
            query="persistent saved search alert",
            sources=["openalex"],
            filters=SearchFilters(open_access_only=True),
            alert_enabled=True,
        )
    )
    service.record_history(
        query="persistent saved search alert",
        normalized_query="persistent saved search alert",
        sources=["openalex"],
        result_count=2,
    )
    service.update_trending([make_paper(title="Persistent Retrieval Paper")], ["Persistent Retrieval"])

    SearchWorkspaceService._saved_searches = []
    SearchWorkspaceService._history = []
    SearchWorkspaceService._trending_papers = []
    SearchWorkspaceService._trending_topics = []
    SearchWorkspaceService._scopes = {}
    SearchWorkspaceService._loaded = False

    reloaded = SearchWorkspaceService()

    assert reloaded.list_saved_searches()[0].query == "persistent saved search alert"
    assert reloaded.list_history()[0].result_count == 2
    assert reloaded.trending().topics == ["Persistent Retrieval"]
    assert reloaded.trending().papers[0].title == "Persistent Retrieval Paper"


def test_workspace_scopes_saved_searches_and_history_per_user() -> None:
    service = SearchWorkspaceService()
    service.save_search(
        SavedSearchRequest(
            name="User A",
            query="alpha retrieval",
            sources=["openalex"],
            filters=SearchFilters(),
        ),
        user_id="user-a",
    )
    service.save_search(
        SavedSearchRequest(
            name="User B",
            query="beta retrieval",
            sources=["arxiv"],
            filters=SearchFilters(),
        ),
        user_id="user-b",
    )
    service.record_history(
        query="alpha retrieval",
        normalized_query="alpha retrieval",
        sources=["openalex"],
        result_count=1,
        user_id="user-a",
    )

    assert [item.query for item in service.list_saved_searches(user_id="user-a")] == ["alpha retrieval"]
    assert [item.query for item in service.list_saved_searches(user_id="user-b")] == ["beta retrieval"]
    assert service.list_history(user_id="user-a")
    assert service.list_history(user_id="user-b") == []


def test_workspace_runs_saved_search_alerts_for_user_scope() -> None:
    service = SearchWorkspaceService()
    saved = service.save_search(
        SavedSearchRequest(
            name="Retrieval Alerts",
            query="retrieval benchmark",
            sources=["openalex"],
            filters=SearchFilters(),
            alert_enabled=True,
            alert_cadence="daily",
        ),
        user_id="alerts-user",
    )
    service.update_trending(
        [make_paper(title="Retrieval Benchmark Dataset", recommendation_reason="New benchmark match")],
        ["Retrieval"],
        user_id="alerts-user",
    )

    result = service.run_alerts(user_id="alerts-user")

    assert result.evaluated_count == 1
    assert result.triggered_count == 1
    assert result.notifications[0]["saved_search_id"] == saved.id
    assert service.list_saved_searches(user_id="alerts-user")[0].new_match_count == 1


def test_workspace_exports_csv_and_bibtex() -> None:
    service = SearchWorkspaceService()
    papers = [make_paper()]

    csv_export = service.export_results(papers, "csv")
    bibtex_export = service.export_results(papers, "bibtex")

    assert csv_export.filename.endswith(".csv")
    assert "paper_id,title,year" in csv_export.content
    assert bibtex_export.filename.endswith(".bib")
    assert "@article{" in bibtex_export.content
