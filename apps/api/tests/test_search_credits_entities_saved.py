"""Credits ledger, saved-search management and researcher/institution data. No live services."""

import asyncio
import json

import httpx
import pytest

from app.schemas.search import SavedSearchRequest, SearchFilters
from app.services.credits.service import CreditLimitReached, CreditService
from app.services.search.entities import EntityNotFound, EntityService
from app.services.search.workspace import SearchWorkspaceService


# --------------------------------------------------------------------------- credits


def test_reserve_commit_refund_and_limits(tmp_path, monkeypatch):
    monkeypatch.setenv("CREDIT_PLAN_LIMITS", json.dumps({"free": {"session": 10, "week": 50, "month": 100}}))
    credits = CreditService(str(tmp_path / "credits.sqlite3"))

    first = credits.reserve("user:a", "research")  # 5
    second = credits.reserve("user:a", "research")  # 10 → at the session limit
    with pytest.raises(CreditLimitReached) as limit:
        credits.reserve("user:a", "ask")
    assert limit.value.scope == "session"

    credits.refund(second)  # failed answer → nothing charged
    credits.commit(first, 0)  # cached answer → free
    session = next(window for window in credits.usage("user:a")["windows"] if window["scope"] == "session")
    assert session["used"] == 0 and session["remaining"] == 10


def test_free_actions_never_reserve(tmp_path):
    credits = CreditService(str(tmp_path / "credits.sqlite3"))
    assert credits.reserve("user:a", "search") is None


def test_users_are_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("CREDIT_PLAN_LIMITS", json.dumps({"free": {"session": 5, "week": 50, "month": 100}}))
    credits = CreditService(str(tmp_path / "credits.sqlite3"))
    credits.commit(credits.reserve("user:a", "research"))
    assert credits.reserve("user:b", "research")  # another user still has credits


# --------------------------------------------------------------------------- saved searches


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("RESORA_SEARCH_WORKSPACE_BACKEND", "json")
    monkeypatch.setattr(SearchWorkspaceService, "_store_path", tmp_path / "workspace.json")
    monkeypatch.setattr(SearchWorkspaceService, "_loaded", False)
    monkeypatch.setattr(SearchWorkspaceService, "_scopes", {})
    monkeypatch.setattr(SearchWorkspaceService, "_saved_searches", [])
    monkeypatch.setattr(SearchWorkspaceService, "_history", [])
    monkeypatch.setattr(SearchWorkspaceService, "_trending_papers", [])
    monkeypatch.setattr(SearchWorkspaceService, "_trending_topics", [])
    return SearchWorkspaceService()


def _request(query="rag evaluation", **kwargs):
    return SavedSearchRequest(name=query, query=query, filters=SearchFilters(), **kwargs)


def test_saved_search_has_no_invented_matches(workspace):
    record = workspace.save_search(_request(alert_enabled=True), user_id="u1")
    assert record.new_match_count == 0 and record.last_triggered_at is None
    alerts = workspace.run_alerts(user_id="u1")
    assert alerts.triggered_count == 0  # nothing matched, so nothing is reported


def test_saving_the_same_search_updates_instead_of_duplicating(workspace):
    first = workspace.save_search(_request(), user_id="u1")
    second = workspace.save_search(_request(alert_cadence="weekly"), user_id="u1")
    assert first.id == second.id
    assert len(workspace.list_saved_searches(user_id="u1")) == 1


def test_update_and_delete_are_scoped_to_the_owner(workspace):
    record = workspace.save_search(_request(), user_id="u1")
    assert workspace.update_saved_search(record.id, {"alert_enabled": False}, user_id="u2") is None
    updated = workspace.update_saved_search(record.id, {"alert_enabled": False, "name": " New name "}, user_id="u1")
    assert updated and updated.alert_enabled is False and updated.name == "New name"
    assert workspace.delete_saved_search(record.id, user_id="u2") is False
    assert workspace.delete_saved_search(record.id, user_id="u1") is True
    assert workspace.list_saved_searches(user_id="u1") == []


# --------------------------------------------------------------------------- researchers & institutions


def _service(routes: dict[str, dict]) -> EntityService:
    def handler(request: httpx.Request) -> httpx.Response:
        for prefix, payload in routes.items():
            if request.url.path.startswith(prefix):
                return httpx.Response(200, json=payload)
        return httpx.Response(404, json={})

    return EntityService(client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_entity_matches_only_when_the_query_names_them():
    service = _service({
        "/autocomplete/authors": {"results": [
            {"id": "https://openalex.org/A5000000001", "display_name": "Geoffrey E. Hinton", "hint": "University of Toronto", "works_count": 400},
            {"id": "https://openalex.org/A5000000002", "display_name": "Learning Person", "hint": "X"},
        ]},
        "/autocomplete/institutions": {"results": []},
    })
    matches = asyncio.run(service.find("geoffrey hinton"))
    assert [item.id for item in matches.researchers] == ["A5000000001"]
    topic_matches = asyncio.run(service.find("deep learning for images"))
    assert topic_matches.researchers == []


def test_researcher_profile_builds_timeline_and_collaborators():
    service = _service({
        "/authors/": {
            "display_name": "Ada Example",
            "works_count": 12,
            "cited_by_count": 340,
            "summary_stats": {"h_index": 7},
            "last_known_institutions": [{"display_name": "Example University"}],
            "topics": [{"display_name": "Graph learning", "count": 5}],
            "counts_by_year": [{"year": 2024, "works_count": 3, "cited_by_count": 50}, {"year": 1990, "works_count": 1}],
        },
        "/works": {"results": [{
            "display_name": "A paper",
            "publication_year": 2024,
            "cited_by_count": 10,
            "authorships": [{"author": {"id": "https://openalex.org/A5000000009", "display_name": "Co Author"}}],
        }]},
    })
    profile = asyncio.run(service.researcher("A5000000003"))
    assert profile.h_index == 7 and profile.affiliations == ["Example University"]
    assert [row.year for row in profile.timeline] == [2024]  # only the last ten years
    assert profile.collaborators[0].id == "A5000000009"
    assert "openalex" not in profile.model_dump_json().lower()


def test_invalid_ids_are_rejected_without_network():
    with pytest.raises(EntityNotFound):
        asyncio.run(_service({}).researcher("../../etc"))
