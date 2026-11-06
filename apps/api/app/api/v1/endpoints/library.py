"""Library API.

Legacy citation routes (/save, /preview, /import) are kept unchanged for the Write tab.
Everything else is the owner-scoped Library: saved papers, projects, collections, notes, ideas, tasks, citations and Ask.
Responses are public DTOs: no owner ids, no database internals, no names of the services metadata came from.
"""

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.api.deps import AuthContext, get_auth_context
from app.core.config import settings
from app.schemas.library import (
    CitationImportRequest,
    CitationImportResponse,
    CitationLibraryRequest,
    CitationLibraryResponse,
    CitationPreviewRequest,
    CitationPreviewResponse,
    LibraryAskRequest,
    LibraryAskResponse,
    LibraryAskSource,
    LibraryBulkRequest,
    LibraryCiteRequest,
    LibraryCiteResponse,
    LibraryExportRequest,
    LibraryExportResponse,
    LibraryImportRequest,
    LibraryImportResponse,
    LibraryItemOut,
    LibraryItemUpdate,
    LibraryListIn,
    LibraryListOut,
    LibraryListUpdate,
    LibraryLookupRequest,
    LibraryNoteIn,
    LibraryNoteOut,
    LibraryNoteUpdate,
    LibraryOverview,
    LibrarySaveRequest,
    LibrarySaveResponse,
    LibraryTaskIn,
    LibraryTaskOut,
    LibraryTaskUpdate,
)
from app.services.library import ask as library_ask
from app.services.library import citations
from app.services.library import resolve
from app.services.library.manager import CitationLibraryService
from app.services.library.store import LibraryLimit, LibraryNotFound, LibraryStore, paper_key

router = APIRouter()
service = CitationLibraryService()
store = LibraryStore()

NOT_FOUND = HTTPException(status_code=404, detail={"code": "not_found"})


# --------------------------------------------------------------------------- legacy routes (unchanged behaviour)


@router.post("/save", response_model=CitationLibraryResponse)
async def save_library_items(payload: CitationLibraryRequest) -> CitationLibraryResponse:
    return service.save(payload)


@router.post("/preview", response_model=CitationPreviewResponse)
async def preview_citation(payload: CitationPreviewRequest) -> CitationPreviewResponse:
    return service.preview(payload)


@router.post("/import", response_model=CitationImportResponse)
async def import_citations(payload: CitationImportRequest) -> CitationImportResponse:
    return service.import_records(payload)


# --------------------------------------------------------------------------- helpers


def _owner(auth: AuthContext) -> str:
    """Same identity rule as Compare: a signed-in account, or (outside production) the per-browser owner header."""
    if (settings.deployment_stage.lower() == "production" and not auth.verified) or not auth.user_id or auth.user_id == "anonymous":
        raise HTTPException(status_code=401, detail={"code": "sign_in_required"})
    return auth.user_id


def _guard(call):
    try:
        return call()
    except LibraryNotFound as error:
        raise NOT_FOUND from error
    except LibraryLimit as error:
        raise HTTPException(status_code=409, detail={"code": "library_full"}) from error


def _scope_items(owner: str, item_ids: list[str] | None, list_id: str | None) -> list[dict]:
    items = store.list_items(owner)
    if list_id:
        members = set(_guard(lambda: store.get_list(owner, list_id))["item_ids"] or [])
        items = [item for item in items if item["id"] in members]
    if item_ids is not None:
        order = {item_id: index for index, item_id in enumerate(item_ids)}
        items = sorted((item for item in items if item["id"] in order), key=lambda item: order[item["id"]])
    return items


# --------------------------------------------------------------------------- overview and items


@router.get("/overview", response_model=LibraryOverview)
def library_overview(auth: AuthContext = Depends(get_auth_context)) -> LibraryOverview:
    return LibraryOverview(**store.overview(_owner(auth)))


@router.get("/items", response_model=list[LibraryItemOut])
def list_items(auth: AuthContext = Depends(get_auth_context)) -> list[LibraryItemOut]:
    return [LibraryItemOut(**item) for item in store.list_items(_owner(auth))]


@router.post("/items", response_model=LibrarySaveResponse)
def save_items(payload: LibrarySaveRequest, auth: AuthContext = Depends(get_auth_context)) -> LibrarySaveResponse:
    owner = _owner(auth)
    items, existing = _guard(lambda: store.add_items(owner, [paper.model_dump() for paper in payload.papers], source=payload.source, list_id=payload.list_id, tags=payload.tags, read_later=payload.read_later))
    if payload.list_id:
        store.touch_list(owner, payload.list_id)
    return LibrarySaveResponse(items=[LibraryItemOut(**item) for item in items], already_saved=existing)


@router.post("/items/lookup")
def lookup_items(payload: LibraryLookupRequest, auth: AuthContext = Depends(get_auth_context)) -> dict[str, list[str | None]]:
    """For each paper (same order), the id of its saved copy or null."""
    owner = _owner(auth)
    keys = [paper_key(doi=paper.doi, arxiv_id=paper.arxiv_id, title=paper.title, year=paper.year) for paper in payload.papers]
    found = store.lookup(owner, keys)
    return {"item_ids": [found.get(key) for key in keys]}


@router.post("/items/bulk")
def bulk_items(payload: LibraryBulkRequest, auth: AuthContext = Depends(get_auth_context)) -> dict[str, int]:
    owner = _owner(auth)
    if payload.action == "set_status" and payload.value not in ("to_read", "reading", "read"):
        raise HTTPException(status_code=422, detail={"code": "invalid_status"})
    if payload.action in {"add_tag", "remove_tag", "add_to_list", "remove_from_list"} and not str(payload.value or "").strip():
        raise HTTPException(status_code=422, detail={"code": "value_required"})
    return {"updated": _guard(lambda: store.bulk(owner, payload.ids, payload.action, payload.value))}


@router.patch("/items/{item_id}", response_model=LibraryItemOut)
def update_item(item_id: str, payload: LibraryItemUpdate, auth: AuthContext = Depends(get_auth_context)) -> LibraryItemOut:
    owner = _owner(auth)
    return LibraryItemOut(**_guard(lambda: store.update_item(owner, item_id, payload.model_dump(exclude_unset=True))))


@router.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: str, auth: AuthContext = Depends(get_auth_context)) -> Response:
    if not store.delete_items(_owner(auth), [item_id]):
        raise NOT_FOUND
    return Response(status_code=204)


# --------------------------------------------------------------------------- projects and collections


@router.get("/lists", response_model=list[LibraryListOut])
def list_lists(kind: Literal["project", "collection"] | None = Query(default=None), auth: AuthContext = Depends(get_auth_context)) -> list[LibraryListOut]:
    return [LibraryListOut(**record) for record in store.list_lists(_owner(auth), kind)]


@router.post("/lists", response_model=LibraryListOut)
def create_list(payload: LibraryListIn, auth: AuthContext = Depends(get_auth_context)) -> LibraryListOut:
    if not payload.name.strip():
        raise HTTPException(status_code=422, detail={"code": "name_required"})
    return LibraryListOut(**store.create_list(_owner(auth), payload.kind, payload.name, payload.description))


@router.get("/lists/{list_id}", response_model=LibraryListOut)
def get_list(list_id: str, auth: AuthContext = Depends(get_auth_context)) -> LibraryListOut:
    owner = _owner(auth)
    return LibraryListOut(**_guard(lambda: store.get_list(owner, list_id)))


@router.patch("/lists/{list_id}", response_model=LibraryListOut)
def update_list(list_id: str, payload: LibraryListUpdate, auth: AuthContext = Depends(get_auth_context)) -> LibraryListOut:
    owner = _owner(auth)
    return LibraryListOut(**_guard(lambda: store.update_list(owner, list_id, payload.name, payload.description)))


@router.delete("/lists/{list_id}", status_code=204)
def delete_list(list_id: str, auth: AuthContext = Depends(get_auth_context)) -> Response:
    owner = _owner(auth)
    _guard(lambda: store.delete_list(owner, list_id))
    return Response(status_code=204)


# --------------------------------------------------------------------------- notes and ideas


@router.get("/notes", response_model=list[LibraryNoteOut])
def list_notes(kind: Literal["note", "idea"] | None = None, project_id: str | None = None, item_id: str | None = None, auth: AuthContext = Depends(get_auth_context)) -> list[LibraryNoteOut]:
    return [LibraryNoteOut(**note) for note in store.list_notes(_owner(auth), kind=kind, project_id=project_id, item_id=item_id)]


@router.post("/notes", response_model=LibraryNoteOut)
def create_note(payload: LibraryNoteIn, auth: AuthContext = Depends(get_auth_context)) -> LibraryNoteOut:
    owner = _owner(auth)
    if not (payload.body.strip() or (payload.title or "").strip() or (payload.quote or "").strip()):
        raise HTTPException(status_code=422, detail={"code": "empty_note"})
    return LibraryNoteOut(**_guard(lambda: store.create_note(owner, payload.model_dump())))


@router.patch("/notes/{note_id}", response_model=LibraryNoteOut)
def update_note(note_id: str, payload: LibraryNoteUpdate, auth: AuthContext = Depends(get_auth_context)) -> LibraryNoteOut:
    owner = _owner(auth)
    return LibraryNoteOut(**_guard(lambda: store.update_note(owner, note_id, payload.model_dump(exclude_unset=True))))


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: str, auth: AuthContext = Depends(get_auth_context)) -> Response:
    owner = _owner(auth)
    _guard(lambda: store.delete_note(owner, note_id))
    return Response(status_code=204)


# --------------------------------------------------------------------------- tasks


@router.get("/tasks", response_model=list[LibraryTaskOut])
def list_tasks(project_id: str | None = None, auth: AuthContext = Depends(get_auth_context)) -> list[LibraryTaskOut]:
    return [LibraryTaskOut(**task) for task in store.list_tasks(_owner(auth), project_id=project_id)]


@router.post("/tasks", response_model=LibraryTaskOut)
def create_task(payload: LibraryTaskIn, auth: AuthContext = Depends(get_auth_context)) -> LibraryTaskOut:
    owner = _owner(auth)
    if not payload.title.strip():
        raise HTTPException(status_code=422, detail={"code": "title_required"})
    return LibraryTaskOut(**_guard(lambda: store.create_task(owner, payload.model_dump())))


@router.patch("/tasks/{task_id}", response_model=LibraryTaskOut)
def update_task(task_id: str, payload: LibraryTaskUpdate, auth: AuthContext = Depends(get_auth_context)) -> LibraryTaskOut:
    owner = _owner(auth)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("due_date") == "":
        changes["due_date"] = None
    return LibraryTaskOut(**_guard(lambda: store.update_task(owner, task_id, changes)))


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: str, auth: AuthContext = Depends(get_auth_context)) -> Response:
    owner = _owner(auth)
    _guard(lambda: store.delete_task(owner, task_id))
    return Response(status_code=204)


# --------------------------------------------------------------------------- citations


@router.post("/citations/format", response_model=LibraryCiteResponse)
def format_citations(payload: LibraryCiteRequest, auth: AuthContext = Depends(get_auth_context)) -> LibraryCiteResponse:
    items = _scope_items(_owner(auth), payload.item_ids, payload.list_id)
    return LibraryCiteResponse(style=payload.style, entries=citations.bibliography(citations.refs_from_items(items), payload.style))


@router.post("/citations/export", response_model=LibraryExportResponse)
def export_citations(payload: LibraryExportRequest, auth: AuthContext = Depends(get_auth_context)) -> LibraryExportResponse:
    items = _scope_items(_owner(auth), payload.item_ids, payload.list_id)
    if not items:
        raise HTTPException(status_code=422, detail={"code": "nothing_to_export"})
    content, extension, mime = citations.export(citations.refs_from_items(items), payload.format, payload.style)
    return LibraryExportResponse(content=content, filename=f"resora-library.{extension}", mime=mime, count=len(items))


@router.post("/citations/import", response_model=LibraryImportResponse)
async def import_library(payload: LibraryImportRequest, auth: AuthContext = Depends(get_auth_context)) -> LibraryImportResponse:
    owner = _owner(auth)
    fmt = citations.detect_format(payload.content, payload.filename) if payload.format == "auto" else payload.format
    not_found: list[str] = []
    if fmt == "ids":
        identifiers = citations.parse_identifiers(payload.content)
        if not identifiers:
            raise HTTPException(status_code=422, detail={"code": "nothing_to_import"})
        resolved = await resolve.resolve_identifiers(identifiers)
        papers = [paper for _, paper in resolved if paper]
        not_found = [identifier for identifier, paper in resolved if not paper]
    else:
        try:
            papers = citations.parse(payload.content, fmt)
        except (ValueError, KeyError, TypeError) as error:
            raise HTTPException(status_code=422, detail={"code": "unreadable_file"}) from error
    if not papers:
        if not_found:
            return LibraryImportResponse(format=fmt, added=0, already_saved=0, items=[], not_found=not_found)
        raise HTTPException(status_code=422, detail={"code": "nothing_to_import"})
    tags = payload.tags

    def save():
        all_items, existing = [], []
        for paper in papers:
            extra = [*tags, *(paper.pop("tags", None) or [])]
            items, already = store.add_items(owner, [paper], source="import", list_id=payload.list_id, tags=extra)
            all_items += items
            existing += already
        return all_items, existing

    items, existing = await asyncio.to_thread(lambda: _guard(save))
    unique = {item["id"]: item for item in items}
    return LibraryImportResponse(
        format=fmt,
        added=len([item_id for item_id in unique if item_id not in set(existing)]),
        already_saved=len(set(existing)),
        items=[LibraryItemOut(**item) for item in unique.values()],
        not_found=not_found,
    )


# --------------------------------------------------------------------------- ask


@router.post("/ask", response_model=LibraryAskResponse)
async def ask_library(payload: LibraryAskRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> LibraryAskResponse:
    owner = _owner(auth)

    def gather():
        items = store.list_items(owner)
        notes = store.list_notes(owner)
        if payload.project_id:
            project = store.get_list(owner, payload.project_id)
            members = set(project["item_ids"] or [])
            items = [item for item in items if item["id"] in members]
            notes = [note for note in notes if note.get("project_id") == payload.project_id or note.get("item_id") in members]
        return items, notes

    items, notes = await asyncio.to_thread(lambda: _guard(gather))
    ranked, window_applied = library_ask.search_memory(items, notes, payload.question)
    sources = [
        LibraryAskSource(n=index, kind=source["kind"], id=source["id"], title=source["title"][:300], snippet=source["snippet"], item_id=source.get("item_id"))
        for index, source in enumerate(ranked, start=1)
    ]
    if not ranked:
        return LibraryAskResponse(mode="matches", not_found=True, sources=[], window_applied=window_applied)

    from app.api.v1.endpoints.reader import _plan, _viewer_key
    from app.services.credits.service import CreditLimitReached, get_credit_service

    credits = get_credit_service()
    try:
        reservation = credits.reserve(_viewer_key(auth, request), "ask", plan=_plan(auth))
    except CreditLimitReached:
        return LibraryAskResponse(mode="matches", sources=sources, window_applied=window_applied)
    try:
        result = await asyncio.to_thread(library_ask.ai_answer, payload.question, ranked, payload.language)
    except Exception:  # noqa: BLE001 - no answer: the ranked matches are still useful
        credits.refund(reservation)
        return LibraryAskResponse(mode="matches", sources=sources, window_applied=window_applied)
    used = max(1, credits.cost("ask"))
    credits.commit(reservation, used)
    return LibraryAskResponse(mode="answer", answer=result["answer"], not_found=result["not_found"], sources=sources, window_applied=window_applied, credits_used=used)
