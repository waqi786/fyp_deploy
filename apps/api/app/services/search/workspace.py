from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.schemas.paper import PaperRecord
from app.schemas.search import (
    SearchAlertPreview,
    SavedSearchRecord,
    SavedSearchRequest,
    SearchAlertRunResponse,
    SearchExportResponse,
    SearchFilters,
    SearchHistoryItem,
    SearchWorkspaceSnapshot,
    TrendingPaperItem,
    TrendingSearchResponse,
)


class SearchWorkspaceService:
    _saved_searches: list[SavedSearchRecord] = []
    _history: list[SearchHistoryItem] = []
    _trending_papers: list[TrendingPaperItem] = []
    _trending_topics: list[str] = []
    _scopes: dict[str, dict[str, list]] = {}
    _loaded = False
    _store_path = Path(os.getenv("RESORA_SEARCH_WORKSPACE_FILE", "storage/search_workspace.json"))
    _snapshot_id = os.getenv("RESORA_SEARCH_WORKSPACE_ID", "default")

    def __init__(self) -> None:
        type(self)._ensure_loaded()

    @classmethod
    def _ensure_loaded(cls) -> None:
        if cls._loaded:
            return

        cls._loaded = True
        if cls._postgres_enabled():
            if cls._load_from_postgres():
                return

        if not cls._store_path.exists():
            cls._sync_default_scope()
            return

        try:
            payload = json.loads(cls._store_path.read_text(encoding="utf-8"))
            if "scopes" in payload:
                cls._scopes = {}
                for scope, state in payload.get("scopes", {}).items():
                    cls._scopes[str(scope)] = cls._validated_state(state)
                cls._restore_legacy_default_state()
            else:
                cls._saved_searches = [
                    SavedSearchRecord.model_validate(item) for item in payload.get("saved_searches", [])
                ][:15]
                cls._history = [SearchHistoryItem.model_validate(item) for item in payload.get("history", [])][:20]
                cls._trending_papers = [
                    TrendingPaperItem.model_validate(item) for item in payload.get("trending_papers", [])
                ][:6]
                cls._trending_topics = [str(topic) for topic in payload.get("trending_topics", [])][:8]
                cls._sync_default_scope()
        except (OSError, json.JSONDecodeError, ValueError):
            cls._saved_searches = []
            cls._history = []
            cls._trending_papers = []
            cls._trending_topics = []
            cls._scopes = {}

    @classmethod
    def _persist(cls) -> None:
        if cls._postgres_enabled() and cls._persist_to_postgres():
            return

        try:
            cls._store_path.parent.mkdir(parents=True, exist_ok=True)
            cls._store_path.write_text(
                json.dumps(
                    {
                        "scopes": {
                            scope: cls._state_payload(state)
                            for scope, state in cls._scopes.items()
                        },
                        "saved_searches": [item.model_dump(mode="json") for item in cls._saved_searches],
                        "history": [item.model_dump(mode="json") for item in cls._history],
                        "trending_papers": [item.model_dump(mode="json") for item in cls._trending_papers],
                        "trending_topics": cls._trending_topics,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            # Search must keep working even if a read-only deployment disables local workspace persistence.
            return

    @classmethod
    def _scope(cls, user_id: str | None = None) -> str:
        cleaned = (user_id or "anonymous").strip()
        return cleaned or "anonymous"

    @classmethod
    def _validated_state(cls, state: dict) -> dict[str, list]:
        return {
            "saved_searches": [SavedSearchRecord.model_validate(item) for item in state.get("saved_searches", [])][:15],
            "history": [SearchHistoryItem.model_validate(item) for item in state.get("history", [])][:20],
            "trending_papers": [TrendingPaperItem.model_validate(item) for item in state.get("trending_papers", [])][:6],
            "trending_topics": [str(topic) for topic in state.get("trending_topics", [])][:8],
        }

    @classmethod
    def _empty_state(cls) -> dict[str, list]:
        return {"saved_searches": [], "history": [], "trending_papers": [], "trending_topics": []}

    @classmethod
    def _state_payload(cls, state: dict[str, list]) -> dict[str, list]:
        return {
            "saved_searches": [item.model_dump(mode="json") for item in state.get("saved_searches", [])],
            "history": [item.model_dump(mode="json") for item in state.get("history", [])],
            "trending_papers": [item.model_dump(mode="json") for item in state.get("trending_papers", [])],
            "trending_topics": list(state.get("trending_topics", [])),
        }

    @classmethod
    def _sync_default_scope(cls) -> None:
        cls._scopes.setdefault(
            "anonymous",
            {
                "saved_searches": cls._saved_searches,
                "history": cls._history,
                "trending_papers": cls._trending_papers,
                "trending_topics": cls._trending_topics,
            },
        )

    @classmethod
    def _restore_legacy_default_state(cls) -> None:
        state = cls._scopes.get("anonymous") or cls._empty_state()
        cls._saved_searches = list(state["saved_searches"])
        cls._history = list(state["history"])
        cls._trending_papers = list(state["trending_papers"])
        cls._trending_topics = list(state["trending_topics"])

    @classmethod
    def _state(cls, user_id: str | None = None) -> dict[str, list]:
        scope = cls._scope(user_id)
        if scope not in cls._scopes:
            cls._scopes[scope] = cls._empty_state()
        return cls._scopes[scope]

    @classmethod
    def _commit_state(cls, user_id: str | None, state: dict[str, list]) -> None:
        cls._scopes[cls._scope(user_id)] = state
        if cls._scope(user_id) == "anonymous":
            cls._restore_legacy_default_state()

    @classmethod
    def _postgres_enabled(cls) -> bool:
        return os.getenv("RESORA_SEARCH_WORKSPACE_BACKEND", "json").lower() == "postgres"

    @classmethod
    def _postgres_dsn(cls) -> str | None:
        dsn = os.getenv("RESORA_SEARCH_WORKSPACE_DATABASE_URL") or os.getenv("DATABASE_URL")
        if not dsn:
            return None
        return dsn.replace("postgresql+psycopg://", "postgresql://", 1)

    @classmethod
    def _connect_postgres(cls):
        dsn = cls._postgres_dsn()
        if not dsn:
            return None
        try:
            import psycopg

            return psycopg.connect(dsn, connect_timeout=5)
        except Exception:
            return None

    @classmethod
    def _ensure_postgres_schema(cls, connection) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                create table if not exists resora_search_workspace_snapshots (
                    id text primary key,
                    saved_searches jsonb not null default '[]'::jsonb,
                    history jsonb not null default '[]'::jsonb,
                    trending_papers jsonb not null default '[]'::jsonb,
                    trending_topics jsonb not null default '[]'::jsonb,
                    updated_at timestamptz not null default now()
                )
                """
            )
            # Per-user workspaces (older deployments stored only the shared anonymous state).
            cursor.execute(
                "alter table resora_search_workspace_snapshots add column if not exists scopes jsonb not null default '{}'::jsonb"
            )
        connection.commit()

    @classmethod
    def _load_from_postgres(cls) -> bool:
        connection = cls._connect_postgres()
        if connection is None:
            return False
        try:
            with connection:
                cls._ensure_postgres_schema(connection)
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        select saved_searches, history, trending_papers, trending_topics, scopes
                        from resora_search_workspace_snapshots
                        where id = %s
                        """,
                        (cls._snapshot_id,),
                    )
                    row = cursor.fetchone()
            if not row:
                cls._sync_default_scope()
                return True
            saved_searches, history, trending_papers, trending_topics, scopes = row
            if isinstance(scopes, dict) and scopes:
                cls._scopes = {str(scope): cls._validated_state(state) for scope, state in scopes.items()}
                cls._restore_legacy_default_state()
                return True
            cls._saved_searches = [SavedSearchRecord.model_validate(item) for item in saved_searches][:15]
            cls._history = [SearchHistoryItem.model_validate(item) for item in history][:20]
            cls._trending_papers = [TrendingPaperItem.model_validate(item) for item in trending_papers][:6]
            cls._trending_topics = [str(topic) for topic in trending_topics][:8]
            cls._sync_default_scope()
            return True
        except Exception:
            return False
        finally:
            connection.close()

    @classmethod
    def _persist_to_postgres(cls) -> bool:
        connection = cls._connect_postgres()
        if connection is None:
            return False
        try:
            payload = {
                "saved_searches": [item.model_dump(mode="json") for item in cls._saved_searches],
                "history": [item.model_dump(mode="json") for item in cls._history],
                "trending_papers": [item.model_dump(mode="json") for item in cls._trending_papers],
                "trending_topics": cls._trending_topics,
            }
            with connection:
                cls._ensure_postgres_schema(connection)
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        insert into resora_search_workspace_snapshots
                            (id, saved_searches, history, trending_papers, trending_topics, scopes, updated_at)
                        values (%s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, now())
                        on conflict (id) do update set
                            saved_searches = excluded.saved_searches,
                            history = excluded.history,
                            trending_papers = excluded.trending_papers,
                            trending_topics = excluded.trending_topics,
                            scopes = excluded.scopes,
                            updated_at = now()
                        """,
                        (
                            cls._snapshot_id,
                            json.dumps(payload["saved_searches"]),
                            json.dumps(payload["history"]),
                            json.dumps(payload["trending_papers"]),
                            json.dumps(payload["trending_topics"]),
                            json.dumps({scope: cls._state_payload(state) for scope, state in cls._scopes.items()}),
                        ),
                    )
            return True
        except Exception:
            return False
        finally:
            connection.close()

    def record_history(
        self,
        *,
        query: str,
        normalized_query: str,
        sources: list[str],
        result_count: int,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> str:
        cls = type(self)
        cls._ensure_loaded()
        state = cls._state(user_id)
        resolved_session_id = session_id or f"search-{uuid4().hex[:12]}"
        timestamp = datetime.now(UTC).isoformat()
        item = SearchHistoryItem(
            session_id=resolved_session_id,
            query=query,
            normalized_query=normalized_query,
            sources=sources,
            created_at=timestamp,
            result_count=result_count,
            resumable_url=f"/search?session={resolved_session_id}",
        )
        state["history"] = [item, *[entry for entry in state["history"] if entry.session_id != resolved_session_id]][:20]
        cls._commit_state(user_id, state)
        cls._persist()
        return resolved_session_id

    def save_search(self, payload: SavedSearchRequest, *, user_id: str | None = None) -> SavedSearchRecord:
        cls = type(self)
        cls._ensure_loaded()
        state = cls._state(user_id)
        created_at = datetime.now(UTC).isoformat()
        signature = _saved_signature(payload.query, payload.filters)
        existing = next((item for item in state["saved_searches"] if _saved_signature(item.query, item.filters) == signature), None)
        record = SavedSearchRecord(
            id=existing.id if existing else f"saved-{uuid4().hex[:10]}",
            name=payload.name.strip(),
            query=payload.query.strip(),
            sources=payload.sources,
            filters=payload.filters,
            alert_enabled=payload.alert_enabled,
            alert_cadence=payload.alert_cadence,
            created_at=existing.created_at if existing else created_at,
            last_triggered_at=existing.last_triggered_at if existing else None,
            new_match_count=existing.new_match_count if existing else 0,
        )
        others = [item for item in state["saved_searches"] if item.id != record.id]
        state["saved_searches"] = [record, *others[:14]]
        cls._commit_state(user_id, state)
        cls._persist()
        return record

    def update_saved_search(self, saved_id: str, changes: dict, *, user_id: str | None = None) -> SavedSearchRecord | None:
        """Rename a saved search or change its alert (on/off, cadence). Only the owner's searches are visible here."""
        cls = type(self)
        cls._ensure_loaded()
        state = cls._state(user_id)
        allowed = {key: value for key, value in changes.items() if key in {"name", "alert_enabled", "alert_cadence"} and value is not None}
        updated: SavedSearchRecord | None = None
        records = []
        for item in state["saved_searches"]:
            if item.id == saved_id:
                if "name" in allowed:
                    allowed["name"] = str(allowed["name"]).strip()
                updated = item.model_copy(update=allowed)
                records.append(updated)
            else:
                records.append(item)
        if updated is None:
            return None
        state["saved_searches"] = records
        cls._commit_state(user_id, state)
        cls._persist()
        return updated

    def delete_saved_search(self, saved_id: str, *, user_id: str | None = None) -> bool:
        cls = type(self)
        cls._ensure_loaded()
        state = cls._state(user_id)
        remaining = [item for item in state["saved_searches"] if item.id != saved_id]
        if len(remaining) == len(state["saved_searches"]):
            return False
        state["saved_searches"] = remaining
        cls._commit_state(user_id, state)
        cls._persist()
        return True

    def list_saved_searches(self, *, user_id: str | None = None) -> list[SavedSearchRecord]:
        type(self)._ensure_loaded()
        return list(type(self)._state(user_id)["saved_searches"])

    def list_history(self, *, user_id: str | None = None) -> list[SearchHistoryItem]:
        type(self)._ensure_loaded()
        return list(type(self)._state(user_id)["history"])

    def snapshot(self, *, user_id: str | None = None) -> SearchWorkspaceSnapshot:
        return SearchWorkspaceSnapshot(
            saved_searches=self.list_saved_searches(user_id=user_id),
            history=self.list_history(user_id=user_id),
            alert_previews=self._alert_previews(user_id=user_id),
        )

    def update_trending(self, papers: list[PaperRecord], topics: list[str], *, user_id: str | None = None) -> None:
        cls = type(self)
        cls._ensure_loaded()
        state = cls._state(user_id)
        state["trending_topics"] = topics[:8]
        state["trending_papers"] = [
            TrendingPaperItem(
                title=paper.title,
                source=paper.source,
                year=paper.year,
                reason=paper.recommendation_reason or paper.cluster_label or "High discovery relevance",
            )
            for paper in papers[:6]
        ]
        cls._commit_state(user_id, state)
        cls._persist()

    def trending(self, *, user_id: str | None = None) -> TrendingSearchResponse:
        cls = type(self)
        cls._ensure_loaded()
        state = cls._state(user_id)
        return TrendingSearchResponse(topics=list(state["trending_topics"]), papers=list(state["trending_papers"]))

    def _alert_previews(self, *, user_id: str | None = None) -> list[SearchAlertPreview]:
        type(self)._ensure_loaded()
        state = type(self)._state(user_id)
        previews = []
        for saved in state["saved_searches"][:6]:
            if not saved.alert_enabled:
                continue
            matched = [paper.title for paper in state["trending_papers"] if _query_overlap(saved.query, f"{paper.title} {paper.reason}")][:3]
            previews.append(
                SearchAlertPreview(
                    saved_search_id=saved.id,
                    query=saved.query,
                    cadence=saved.alert_cadence,
                    new_match_count=saved.new_match_count,
                    matched_titles=matched,
                )
            )
        return previews

    def run_alerts(self, *, user_id: str | None = None) -> SearchAlertRunResponse:
        cls = type(self)
        cls._ensure_loaded()
        state = cls._state(user_id)
        timestamp = datetime.now(UTC).isoformat()
        notifications: list[dict[str, str | int | list[str]]] = []
        updated_saved_searches = []
        for saved in state["saved_searches"]:
            if not saved.alert_enabled:
                updated_saved_searches.append(saved)
                continue
            matched_titles = [
                paper.title
                for paper in state["trending_papers"]
                if _query_overlap(saved.query, f"{paper.title} {paper.reason}")
            ][:5]
            new_count = len(matched_titles)
            updated = saved.model_copy(
                update={
                    "last_triggered_at": timestamp if new_count else saved.last_triggered_at,
                    "new_match_count": new_count,
                }
            )
            updated_saved_searches.append(updated)
            if new_count:
                notifications.append(
                    {
                        "saved_search_id": saved.id,
                        "query": saved.query,
                        "cadence": saved.alert_cadence,
                        "new_match_count": new_count,
                        "matched_titles": matched_titles,
                    }
                )
        state["saved_searches"] = updated_saved_searches
        cls._commit_state(user_id, state)
        cls._persist()
        return SearchAlertRunResponse(
            user_id=cls._scope(user_id),
            evaluated_count=len(updated_saved_searches),
            triggered_count=len(notifications),
            notifications=notifications,
            generated_at=timestamp,
        )

    def export_results(self, papers: list[PaperRecord], export_format: str) -> SearchExportResponse:
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        if export_format == "bibtex":
            entries = []
            for paper in papers:
                key = f"{(paper.authors[0].get('name', 'resora').split()[-1]).lower() if paper.authors else 'resora'}{paper.year or 'nd'}"
                author_names = " and ".join(author.get("name", "Unknown Author") for author in paper.authors) or "Unknown Author"
                entries.append(
                    "\n".join(
                        [
                            f"@article{{{key},",
                            f"  title = {{{paper.title}}},",
                            f"  author = {{{author_names}}},",
                            f"  year = {{{paper.year or ''}}},",
                            f"  journal = {{{paper.venue or ''}}},",
                            f"  doi = {{{paper.doi or ''}}},",
                            f"  url = {{{paper.url or ''}}}",
                            "}",
                        ]
                    )
                )
            return SearchExportResponse(format="bibtex", filename=f"resora-search-{timestamp}.bib", content="\n\n".join(entries))

        header = "paper_id,title,year,source,venue,citation_count,open_access,doi,url"
        rows = [
            ",".join(
                [
                    paper.paper_id,
                    _csv_escape(paper.title),
                    str(paper.year or ""),
                    paper.source,
                    _csv_escape(paper.venue or ""),
                    str(paper.citation_count),
                    str(paper.is_open_access).lower(),
                    paper.doi or "",
                    paper.url or "",
                ]
            )
            for paper in papers
        ]
        return SearchExportResponse(format="csv", filename=f"resora-search-{timestamp}.csv", content="\n".join([header, *rows]))


def _csv_escape(value: str) -> str:
    escaped = value.replace('"', '""')
    return f'"{escaped}"'


def _saved_signature(query: str, filters: SearchFilters) -> str:
    return json.dumps([" ".join(query.casefold().split()), filters.model_dump(mode="json")], sort_keys=True)


def _query_overlap(query: str, text: str) -> bool:
    query_terms = {token.lower() for token in query.split() if len(token) > 2}
    text_terms = {token.lower().strip(".,:;!?()[]") for token in text.split()}
    return bool(query_terms & text_terms)
