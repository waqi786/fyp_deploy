"""Search API.

Public responses never expose connector names, provider details, scores used for debugging or
operational diagnostics. Everything a user sees goes through the presenter helpers below.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, AsyncIterator, Callable

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.api.deps import AuthContext, get_auth_context
from app.core.config import settings
from app.schemas.paper import PaperRecord, PaperSearchResponse
from app.schemas.entities import EntityMatches, InstitutionProfile, ResearcherProfile
from app.schemas.research import AskRequest, CreditEstimate, ResearchAnswer, ResearchRequest
from app.schemas.search import (
    SavedSearchRecord,
    SavedSearchRequest,
    SavedSearchUpdate,
    SearchAlertRunResponse,
    SearchExportRequest,
    SearchExportResponse,
    SearchHistoryItem,
    SearchRequest,
    SearchWorkspaceSnapshot,
    TrendingSearchResponse,
)
from app.services.credits.service import CreditLimitReached, get_credit_service
from app.services.notifications.delivery import AlertDeliveryService
from app.services.search.entities import EntityNotFound, EntityUnavailable, get_entity_service
from app.services.search.research import ResearchService, ResearchUnavailable, detect_identifier, paper_matches_identifier
from app.services.search.service import FederatedSearchService
from app.services.search.translation import TranslationUnavailable, get_translation_retry_status, translate_batch, translation_metrics
from app.services.search.ui_copy import UnsupportedLanguage, get_ui_copy_service
from app.services.search.workspace import SearchWorkspaceService

logger = logging.getLogger(__name__)

router = APIRouter()
service = FederatedSearchService()
workspace = SearchWorkspaceService()
delivery = AlertDeliveryService()
research = ResearchService()
RESEARCH_PAGE_SIZE = 20

MAX_QUERY_LENGTH = 500
MAX_PAGE_SIZE = 50
KEEPALIVE_SECONDS = 10.0
PUBLIC_SOURCE_LABEL = "research"
ENGLISH_CODES = {"en", "en-us", "en-gb"}
# Identifiers that are useful to users (citation managers, DOI links). Connector-specific IDs are dropped.
PUBLIC_EXTERNAL_ID_KEYS = {"doi", "pmid", "pmcid", "arxiv", "isbn", "issn"}
# search_insights keys that describe internal machinery and must never reach the browser.
PRIVATE_INSIGHT_MARKERS = ("source", "provider", "model", "dedup", "cache", "debug", "latency", "connector", "score")

GENERIC_ERROR = "Search is temporarily unavailable. Please try again."


# --------------------------------------------------------------------------- helpers


def _admin_user_ids() -> set[str]:
    raw = ",".join(
        value
        for value in (
            getattr(settings, "admin_user_ids", "") or "",
            getattr(settings, "translation_admin_user_ids", "") or "",
        )
        if value
    )
    return {item.strip() for item in raw.split(",") if item.strip()}


def _is_admin(auth: AuthContext) -> bool:
    return bool(getattr(auth, "verified", False)) and auth.user_id in _admin_user_ids()


def _normalize_request(payload: SearchRequest) -> SearchRequest:
    """Validate and clamp user input before any work is done."""
    query = (payload.query or "").strip()
    if not query:
        raise HTTPException(status_code=422, detail="Please enter a search query.")
    if len(query) > MAX_QUERY_LENGTH:
        raise HTTPException(status_code=422, detail=f"Search queries can be at most {MAX_QUERY_LENGTH} characters.")
    updates: dict[str, Any] = {"query": query}
    if payload.limit is not None:
        updates["limit"] = max(1, min(int(payload.limit), MAX_PAGE_SIZE))
    if payload.page is not None:
        updates["page"] = max(1, int(payload.page))
    return payload.model_copy(update=updates)


def _wants_translation(payload: SearchRequest) -> bool:
    target = (payload.target_language or payload.language or "en").strip().lower()
    return bool(payload.translate_results) and target not in ENGLISH_CODES


def _public_paper(paper: PaperRecord) -> PaperRecord:
    """Hide which connector a paper came from while keeping user-useful identifiers."""
    updates: dict[str, Any] = {"source": PUBLIC_SOURCE_LABEL}
    fields = type(paper).model_fields
    if "all_sources" in fields:
        updates["all_sources"] = [PUBLIC_SOURCE_LABEL]
    if "external_ids" in fields:
        external_ids = getattr(paper, "external_ids", None) or {}
        updates["external_ids"] = {
            key: value for key, value in external_ids.items() if str(key).lower() in PUBLIC_EXTERNAL_ID_KEYS
        }
    return paper.model_copy(update=updates)


def _public_papers(raw_papers: Any) -> list[dict[str, Any]]:
    """Validate streamed papers one by one; a single malformed record must not break the stream."""
    if not isinstance(raw_papers, list):
        return []
    papers: list[dict[str, Any]] = []
    for raw in raw_papers:
        try:
            record = raw if isinstance(raw, PaperRecord) else PaperRecord.model_validate(raw)
        except Exception:  # noqa: BLE001 — skip invalid records, keep the stream alive
            logger.debug("Skipping malformed streamed paper", exc_info=True)
            continue
        papers.append(_public_paper(record).model_dump(mode="json"))
    return papers


def _present_search_response(response: PaperSearchResponse) -> PaperSearchResponse:
    """Remove connector internals and operational diagnostics from public search data."""
    insights = {
        key: value
        for key, value in (response.search_insights or {}).items()
        if not any(marker in key.lower() for marker in PRIVATE_INSIGHT_MARKERS)
    }
    updates: dict[str, Any] = {
        "papers": [_public_paper(paper) for paper in response.papers],
        # Partial source outages are handled silently; users only ever see results or a single retry message.
        "source_failures": [],
        "source_coverage": {},
        "search_insights": insights,
        "ranking_explanations": [],
        # Kept on purpose: the client polls these user-scoped jobs to swap in finished translations.
        "translation_retry_ids": list(response.translation_retry_ids or []),
    }
    cache_status = getattr(response, "cache_status", None)
    if cache_status is not None:
        updates["cache_status"] = cache_status.model_copy(update={"inserted_batches": 0, "total_items": 0, "cached_at": None})
    return response.model_copy(update=updates)


def _credit_key(auth: AuthContext, request: Request) -> str:
    """Signed-in users are limited per account; guests per network address (they share one anonymous id)."""
    if getattr(auth, "verified", False) and auth.user_id:
        return f"user:{auth.user_id}"
    host = request.client.host if request.client else "unknown"
    return f"guest:{host}"


def _plan(auth: AuthContext) -> str:
    return str(getattr(auth, "plan", None) or "free")


def _limit_payload(error: CreditLimitReached) -> dict[str, object]:
    from datetime import datetime, timezone

    return {
        "code": "limit_reached",
        "scope": error.scope,
        "resets_at": datetime.fromtimestamp(error.resets_at, tz=timezone.utc).isoformat(),
    }


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


async def _execute_search(
    payload: SearchRequest,
    auth: AuthContext,
    source_event_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> PaperSearchResponse:
    return await service.search(
        payload.query,
        payload.limit,
        payload.sources,
        page=payload.page,
        language=payload.language,
        query_language=payload.query_language,
        paper_language=payload.paper_language,
        target_language=payload.target_language,
        translate_results=payload.translate_results,
        min_citations=payload.min_citations,
        open_access_only=payload.open_access_only,
        study_type=payload.study_type,
        quartile=payload.quartile,
        sample_size_min=payload.sample_size_min,
        year_from=payload.year_from,
        year_to=payload.year_to,
        methodology=payload.methodology,
        author=payload.author,
        venue=payload.venue,
        institution=payload.institution,
        dataset=payload.dataset,
        peer_reviewed_only=payload.peer_reviewed_only,
        preprint_only=payload.preprint_only,
        include_retracted=payload.include_retracted,
        citation_context=payload.citation_context,
        region=payload.region,
        chemical_formula=payload.chemical_formula,
        gene_or_protein=payload.gene_or_protein,
        equipment_or_software=payload.equipment_or_software,
        negative_results_only=payload.negative_results_only,
        temporal_aware=payload.temporal_aware,
        patent_overlap=payload.patent_overlap,
        grey_literature=payload.grey_literature,
        conference_priority=payload.conference_priority,
        cited_by_quality_only=payload.cited_by_quality_only,
        private_search_vault=payload.private_search_vault,
        collaborative_session=payload.collaborative_session,
        search_mode=payload.search_mode,
        query_type=payload.query_type,
        voice_transcript=payload.voice_transcript,
        image_caption=payload.image_caption,
        sort_by=payload.sort_by,
        session_id=payload.session_id,
        save_history=payload.save_history,
        user_id=auth.user_id,
        source_event_callback=source_event_callback,
    )


# --------------------------------------------------------------------------- search


@router.post("/", response_model=PaperSearchResponse)
async def search_papers(payload: SearchRequest, auth: AuthContext = Depends(get_auth_context)) -> PaperSearchResponse:
    payload = _normalize_request(payload)
    try:
        result = await _execute_search(payload, auth)
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001
        logger.exception("Search failed")
        raise HTTPException(status_code=503, detail=GENERIC_ERROR) from error
    return _present_search_response(result)


@router.post("/stream")
async def stream_search_papers(
    request: Request,
    payload: SearchRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> StreamingResponse:
    """Server-sent events: `search_started`, progressive `source_results`, then `done` (or `error`)."""
    payload = _normalize_request(payload)  # invalid input → HTTP 422 before the stream opens
    # When results must be translated, partial English results are not useful to the client; only `done` is sent.
    stream_partials = not _wants_translation(payload)

    async def event_stream() -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

        def on_source_event(event: str, data: dict[str, Any]) -> None:
            # Connectors may report from worker threads; asyncio.Queue is not thread-safe.
            try:
                same_loop = asyncio.get_running_loop() is loop
            except RuntimeError:
                same_loop = False
            if same_loop:
                queue.put_nowait((event, data))
            else:
                loop.call_soon_threadsafe(queue.put_nowait, (event, data))

        def render(event: str, data: dict[str, Any]) -> str | None:
            if event != "source_results" or not stream_partials:
                return None  # source_started / source_failed are internal and never sent
            papers = _public_papers(data.get("papers") if isinstance(data, dict) else None)
            return _sse("source_results", {"papers": papers}) if papers else None

        task = asyncio.create_task(_execute_search(payload, auth, source_event_callback=on_source_event))
        getter: asyncio.Task | None = None
        try:
            yield _sse("search_started", {})
            while True:
                if getter is None:
                    getter = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait({getter, task}, timeout=KEEPALIVE_SECONDS, return_when=asyncio.FIRST_COMPLETED)

                if await request.is_disconnected():
                    return

                if getter in done:
                    event, data = getter.result()
                    getter = None
                    frame = render(event, data)
                    if frame:
                        yield frame
                    continue
                if task in done:
                    break
                yield ": keep-alive\n\n"  # timeout: keep proxies from closing the connection

            # Collect anything the search emitted right before finishing.
            if getter is not None:
                getter.cancel()
                await asyncio.gather(getter, return_exceptions=True)
                if not getter.cancelled() and getter.exception() is None:
                    frame = render(*getter.result())
                    if frame:
                        yield frame
                getter = None
            while not queue.empty():
                frame = render(*queue.get_nowait())
                if frame:
                    yield frame

            result = _present_search_response(task.result())
            yield f"event: done\ndata: {result.model_dump_json()}\n\n"
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Streaming search failed")
            yield _sse("error", {"message": GENERIC_ERROR})
        finally:
            if getter is not None and not getter.done():
                getter.cancel()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------- research with Resora


class _ClientGone(Exception):
    pass


async def _keepalive_until(task: asyncio.Task, request: Request) -> AsyncIterator[str]:
    """Yield SSE keep-alive comments until `task` finishes; stop work if the browser disconnects."""
    while not task.done():
        await asyncio.wait({task}, timeout=KEEPALIVE_SECONDS)
        if await request.is_disconnected():
            task.cancel()
            raise _ClientGone()
        if not task.done():
            yield ": keep-alive\n\n"


def _research_search_request(payload: ResearchRequest) -> SearchRequest:
    return _normalize_request(
        SearchRequest(
            query=payload.query,
            limit=RESEARCH_PAGE_SIZE,
            page=1,
            language=payload.language,
            query_language="auto",
            target_language=payload.language,
            translate_results=payload.language.lower() not in ENGLISH_CODES,
            search_mode="semantic",
            year_from=payload.year_from,
            year_to=payload.year_to,
            open_access_only=payload.open_access_only,
            peer_reviewed_only=payload.peer_reviewed_only,
            preprint_only=payload.preprint_only,
            include_retracted=payload.include_retracted,
            study_type=payload.study_type,
            paper_language=payload.paper_language,
            min_citations=payload.min_citations,
            author=payload.author,
            venue=payload.venue,
        )
    )


@router.get("/research/estimate", response_model=CreditEstimate)
async def research_credit_estimate() -> CreditEstimate:
    """Credits shown to the user before running Research with Resora or Ask."""
    return CreditEstimate(**research.estimate())


@router.post("/research/stream")
async def research_stream(
    request: Request,
    payload: ResearchRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> StreamingResponse:
    """SSE: `step` {step, status} → `papers` {papers, total, query_understanding} → `answer` | `answer_error` → `done`."""
    search_payload = _research_search_request(payload)
    credits = get_credit_service()
    credit_key = _credit_key(auth, request)
    plan = _plan(auth)

    async def event_stream() -> AsyncIterator[str]:
        search_task: asyncio.Task | None = None
        answer_task: asyncio.Task | None = None
        reservation: str | None = None
        try:
            yield _sse("step", {"step": "understand", "status": "active"})
            search_task = asyncio.create_task(_execute_search(search_payload, auth))
            yield _sse("step", {"step": "understand", "status": "done"})
            yield _sse("step", {"step": "search", "status": "active"})
            async for frame in _keepalive_until(search_task, request):
                yield frame
            result = search_task.result()
            public = _present_search_response(result)
            yield _sse("step", {"step": "search", "status": "done"})
            yield _sse(
                "papers",
                {
                    "papers": [paper.model_dump(mode="json") for paper in public.papers],
                    "total": public.total_results,
                    "query_understanding": public.query_understanding,
                    "translation_retry_ids": public.translation_retry_ids,
                },
            )
            if not result.papers:
                yield _sse("done", {})
                return

            yield _sse("step", {"step": "read", "status": "done"})
            try:
                reservation = credits.reserve(credit_key, "research", plan=plan)
            except CreditLimitReached as limit:
                yield _sse("limit", _limit_payload(limit))
                yield _sse("done", {})
                return
            yield _sse("step", {"step": "answer", "status": "active"})
            answer_task = asyncio.create_task(
                research.answer(payload.query, result.papers, language=payload.language, user_id=auth.user_id, kind="research")
            )
            async for frame in _keepalive_until(answer_task, request):
                yield frame
            try:
                answer = answer_task.result()
                credits.commit(reservation, answer.credits_used)
                reservation = None
                yield _sse("answer", answer.model_dump(mode="json"))
            except ResearchUnavailable:
                logger.warning("Research answer unavailable", exc_info=True)
                credits.refund(reservation)
                reservation = None
                yield _sse("answer_error", {"message": "The summary is not available right now. The papers below are ready."})
            yield _sse("step", {"step": "answer", "status": "done"})
            yield _sse("done", {})
        except _ClientGone:
            return
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Research stream failed")
            yield _sse("error", {"message": GENERIC_ERROR})
        finally:
            credits.refund(reservation)  # never charge for work the user did not receive
            for task in (search_task, answer_task):
                if task is not None and not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/ask", response_model=ResearchAnswer)
async def ask_about_results(request: Request, payload: AskRequest, auth: AuthContext = Depends(get_auth_context)) -> ResearchAnswer:
    """Answer a question grounded only in the papers the user is looking at."""
    papers = [
        PaperRecord(
            paper_id=item.paper_id,
            title=item.title,
            abstract=item.abstract,
            year=item.year,
            venue=item.venue,
            source=PUBLIC_SOURCE_LABEL,
        )
        for item in payload.papers
    ]
    credits = get_credit_service()
    try:
        reservation = credits.reserve(_credit_key(auth, request), "ask", plan=_plan(auth))
    except CreditLimitReached as limit:
        raise HTTPException(status_code=402, detail=_limit_payload(limit)) from limit
    try:
        answer = await research.answer(payload.question.strip(), papers, language=payload.language, user_id=auth.user_id, kind="ask")
    except ResearchUnavailable as error:
        credits.refund(reservation)
        raise HTTPException(status_code=503, detail="Answers are not available right now. Please try again shortly.") from error
    except Exception:
        credits.refund(reservation)
        raise
    credits.commit(reservation, answer.credits_used)
    return answer


@router.get("/usage")
async def credit_usage(request: Request, auth: AuthContext = Depends(get_auth_context)) -> dict[str, object]:
    """Usage windows (5-hour session, week, month) for the usage banner."""
    return get_credit_service().usage(_credit_key(auth, request), _plan(auth))


# --------------------------------------------------------------------------- researchers & institutions


async def _translate_profile(profile: ResearcherProfile | InstitutionProfile, language: str, user_id: str | None) -> None:
    """Translate topic names and work titles (public metadata). Failures keep the originals."""
    if not language or language.lower() in ENGLISH_CODES:
        return
    works = [*profile.top_works, *getattr(profile, "recent_works", [])]
    segments = [topic.name for topic in profile.topics] + [work.title for work in works]
    if not segments:
        return
    try:
        translated = await asyncio.to_thread(translate_batch, segments, language, user_id=user_id, user_content=False)
    except (TranslationUnavailable, ValueError):
        return
    for topic, text in zip(profile.topics, translated[: len(profile.topics)]):
        topic.translated_name = text or None
    for work, text in zip(works, translated[len(profile.topics):]):
        work.translated_title = text or None


@router.get("/entities", response_model=EntityMatches)
async def find_entities(q: str = Query(min_length=2, max_length=120)) -> EntityMatches:
    """Researchers and institutions whose name matches the query (for the entity row above results)."""
    try:
        return await get_entity_service().find(q)
    except EntityUnavailable:
        return EntityMatches()


@router.get("/researchers/{entity_id}", response_model=ResearcherProfile)
async def researcher_profile(
    entity_id: str,
    language: str = Query(default="en", max_length=20),
    auth: AuthContext = Depends(get_auth_context),
) -> ResearcherProfile:
    try:
        profile = await get_entity_service().researcher(entity_id)
    except EntityNotFound as error:
        raise HTTPException(status_code=404, detail="Researcher not found") from error
    except EntityUnavailable as error:
        raise HTTPException(status_code=503, detail="This profile is not available right now. Please try again.") from error
    await _translate_profile(profile, language, auth.user_id)
    return profile


@router.get("/institutions/{entity_id}", response_model=InstitutionProfile)
async def institution_profile(
    entity_id: str,
    language: str = Query(default="en", max_length=20),
    auth: AuthContext = Depends(get_auth_context),
) -> InstitutionProfile:
    try:
        profile = await get_entity_service().institution(entity_id)
    except EntityNotFound as error:
        raise HTTPException(status_code=404, detail="Institution not found") from error
    except EntityUnavailable as error:
        raise HTTPException(status_code=503, detail="This profile is not available right now. Please try again.") from error
    await _translate_profile(profile, language, auth.user_id)
    return profile


@router.get("/resolve")
async def resolve_identifier(
    q: str = Query(min_length=4, max_length=300),
    language: str = Query(default="en", max_length=20),
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, object]:
    """If the input is a DOI or arXiv id, return that exact paper so the UI can open it directly."""
    identifier = detect_identifier(q)
    if identifier is None:
        return {"kind": None, "paper": None}
    kind, value = identifier
    lookup = _normalize_request(
        SearchRequest(
            query=value,
            limit=10,
            page=1,
            language=language,
            query_language="en",
            target_language=language,
            translate_results=language.lower() not in ENGLISH_CODES,
            save_history=False,
        )
    )
    try:
        result = await _execute_search(lookup, auth)
    except Exception:  # noqa: BLE001
        logger.warning("Identifier lookup failed", exc_info=True)
        return {"kind": kind, "paper": None}
    match = next((paper for paper in result.papers if paper_matches_identifier(paper, kind, value)), None)
    return {"kind": kind, "paper": _public_paper(match).model_dump(mode="json") if match else None}


# --------------------------------------------------------------------------- saved searches, history, alerts


@router.post("/saved", response_model=SavedSearchRecord)
async def save_search(payload: SavedSearchRequest, auth: AuthContext = Depends(get_auth_context)) -> SavedSearchRecord:
    if not (payload.query or "").strip():
        raise HTTPException(status_code=422, detail="Please enter a search query to save.")
    return workspace.save_search(payload, user_id=auth.user_id)


@router.get("/saved", response_model=list[SavedSearchRecord])
async def list_saved_searches(auth: AuthContext = Depends(get_auth_context)) -> list[SavedSearchRecord]:
    return workspace.list_saved_searches(user_id=auth.user_id)


def _call_workspace(method_names: tuple[str, ...], *args: Any, **kwargs: Any) -> Any:
    """Call the first saved-search method the workspace service implements."""
    for name in method_names:
        method = getattr(workspace, name, None)
        if callable(method):
            return method(*args, **kwargs)
    raise HTTPException(status_code=501, detail="Managing saved searches is not available yet.")


@router.patch("/saved/{saved_id}", response_model=SavedSearchRecord)
async def update_saved_search(saved_id: str, payload: SavedSearchUpdate, auth: AuthContext = Depends(get_auth_context)) -> SavedSearchRecord:
    changes = payload.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Nothing to update.")
    owned = {item.id for item in workspace.list_saved_searches(user_id=auth.user_id)}
    if saved_id not in owned:
        raise HTTPException(status_code=404, detail="Saved search not found")
    result = _call_workspace(("update_saved_search", "update_search"), saved_id, changes, user_id=auth.user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Saved search not found")
    return result


@router.delete("/saved/{saved_id}", status_code=204)
async def delete_saved_search(saved_id: str, auth: AuthContext = Depends(get_auth_context)) -> None:
    owned = {item.id for item in workspace.list_saved_searches(user_id=auth.user_id)}
    if saved_id not in owned:
        raise HTTPException(status_code=404, detail="Saved search not found")
    _call_workspace(("delete_saved_search", "remove_saved_search", "delete_search"), saved_id, user_id=auth.user_id)


@router.get("/history", response_model=list[SearchHistoryItem])
async def list_search_history(auth: AuthContext = Depends(get_auth_context)) -> list[SearchHistoryItem]:
    return workspace.list_history(user_id=auth.user_id)


@router.get("/trending", response_model=TrendingSearchResponse)
async def trending_searches(auth: AuthContext = Depends(get_auth_context)) -> TrendingSearchResponse:
    return workspace.trending(user_id=auth.user_id)


@router.get("/workspace", response_model=SearchWorkspaceSnapshot)
async def search_workspace_snapshot(auth: AuthContext = Depends(get_auth_context)) -> SearchWorkspaceSnapshot:
    return workspace.snapshot(user_id=auth.user_id)


@router.post("/alerts/run", response_model=SearchAlertRunResponse)
async def run_saved_search_alerts(
    auth: AuthContext = Depends(get_auth_context),
    deliver: bool = Query(default=False),
    recipient_email: str | None = Query(default=None),
) -> SearchAlertRunResponse:
    # Only admins may send alert emails to an arbitrary address; everyone else gets their own account email.
    if recipient_email and not _is_admin(auth):
        raise HTTPException(status_code=403, detail="You can only send alerts to your own email address.")
    result = workspace.run_alerts(user_id=auth.user_id)
    if deliver:
        try:
            await delivery.deliver(result, recipient_email=recipient_email)
        except Exception:  # noqa: BLE001 — alert generation succeeded; delivery is retried by the scheduler
            logger.exception("Saved-search alert delivery failed")
    return result


@router.post("/export", response_model=SearchExportResponse)
async def export_search_results(
    payload: SearchExportRequest,
    auth: AuthContext = Depends(get_auth_context),  # noqa: ARG001 — same access rules as the rest of search
) -> SearchExportResponse:
    if not payload.papers:
        raise HTTPException(status_code=422, detail="There are no results to export.")
    return workspace.export_results(payload.papers, payload.format)


# --------------------------------------------------------------------------- translation


@router.get("/ui-copy/{language}")
async def search_ui_copy(language: str) -> dict[str, object]:
    """Complete Search interface text for one language (public labels only; cached after the first request)."""
    try:
        return await asyncio.to_thread(get_ui_copy_service().catalog, language)
    except UnsupportedLanguage as error:
        raise HTTPException(status_code=404, detail="Language not supported") from error


@router.get("/translation/metrics")
async def translation_provider_metrics(auth: AuthContext = Depends(get_auth_context)) -> dict[str, object]:
    if not _is_admin(auth):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"providers": translation_metrics()}


@router.get("/translation/retries/{job_id}")
async def translation_retry_status(job_id: str, auth: AuthContext = Depends(get_auth_context)) -> dict[str, object]:
    status = get_translation_retry_status(job_id, auth.user_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Translation retry not found")
    # Expose only what the client needs to update a result card.
    allowed = {"status", "paper_id", "translated_title", "translated_abstract"}
    return {key: value for key, value in status.items() if key in allowed}


@router.get("/translation/licenses")
async def translation_model_licenses() -> dict[str, object]:
    """Public component/license inventory; contains no keys or user data."""
    endpoint = (getattr(settings, "local_translator_url", None) or os.getenv("LOCAL_TRANSLATOR_URL", "http://translator-local:8091")).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{endpoint}/licenses")
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        return {"status": "translator_unavailable", "installed_packs": []}