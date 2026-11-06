"""Write tab API: Reviews and Drafts (grounded in Library papers), Screening with PRISMA counts, and Check claims.
The legacy /writing and /drafts routes are separate and unchanged."""

import asyncio
import base64
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.deps import AuthContext, get_auth_context
from app.core.config import settings
from app.schemas.write import (
    ClaimCheckRequest,
    ClaimCheckResponse,
    ScreeningCreate,
    ScreeningDecision,
    ScreeningImport,
    ScreeningToLibrary,
    ScreeningUpdate,
    WriteDocument,
    WriteDocumentCreate,
    WriteDocumentSummary,
    WriteDocumentUpdate,
    WriteExportRequest,
    WriteOutlineRequest,
    WriteSectionRequest,
    WriteSourcesAdd,
)
from app.services.library import citations as C
from app.services.library.store import LibraryLimit, LibraryNotFound, LibraryStore
from app.services.write import exporter, grounding
from app.services.write.store import WriteStore

router = APIRouter()
store = WriteStore()
library = LibraryStore()
NOT_FOUND = HTTPException(status_code=404, detail={"code": "not_found"})


def _owner(auth: AuthContext) -> str:
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


def _source(item: dict) -> dict:
    return {key: item.get(key) for key in ("title", "authors", "year", "venue", "doi", "url", "arxiv_id", "abstract")} | {"item_id": item["id"]}


def _library_sources(owner: str, item_ids: list[str], project_id: str | None) -> list[dict]:
    items = library.list_items(owner)
    wanted = list(item_ids)
    if project_id:
        members = _guard(lambda: library.get_list(owner, project_id))["item_ids"] or []
        wanted += [item_id for item_id in members if item_id not in wanted]
    by_id = {item["id"]: item for item in items}
    return [_source(by_id[item_id]) for item_id in wanted if item_id in by_id]


def _present(doc: dict) -> WriteDocument:
    sections = doc["content"].get("sections", [])
    return WriteDocument(**{key: doc[key] for key in ("id", "kind", "title", "style", "language", "citation_style", "project_id", "sources", "created_at", "updated_at")}, sections=sections)


def _sections_from_outline(outline: list[dict]) -> list[dict]:
    return [{"id": uuid4().hex[:10], "heading": item["heading"], "purpose": item["purpose"], "papers": item["papers"], "text": "", "status": "empty", "unsupported": []} for item in outline]


async def _with_credits(auth: AuthContext, request: Request, action: str, work):
    from app.api.v1.endpoints.reader import _limit, _plan, _viewer_key
    from app.services.credits.service import CreditLimitReached, get_credit_service

    credits = get_credit_service()
    try:
        reservation = credits.reserve(_viewer_key(auth, request), action, plan=_plan(auth))
    except CreditLimitReached as error:
        raise _limit(error) from error
    try:
        result = await asyncio.to_thread(work)
    except Exception:
        credits.refund(reservation)
        raise
    used = max(1, credits.cost(action))
    credits.commit(reservation, used)
    return result, used


# --------------------------------------------------------------------------- documents


@router.get("/documents", response_model=list[WriteDocumentSummary])
def list_documents(auth: AuthContext = Depends(get_auth_context)) -> list[WriteDocumentSummary]:
    return [WriteDocumentSummary(**doc) for doc in store.list_documents(_owner(auth))]


@router.post("/documents", response_model=WriteDocument)
def create_document(payload: WriteDocumentCreate, auth: AuthContext = Depends(get_auth_context)) -> WriteDocument:
    owner = _owner(auth)
    if payload.kind == "review" and payload.style not in grounding.STYLES:
        raise HTTPException(status_code=422, detail={"code": "invalid_style"})
    if payload.kind == "draft" and payload.style not in grounding.DRAFT_TYPES:
        raise HTTPException(status_code=422, detail={"code": "invalid_style"})
    sources = _library_sources(owner, payload.item_ids, payload.project_id)
    if payload.kind == "review":
        sections = _sections_from_outline(grounding.outline(sources, payload.style))
    else:
        everyone = list(range(1, len(sources) + 1))
        sections = _sections_from_outline([{"heading": heading, "purpose": purpose, "papers": everyone} for heading, purpose in grounding.DRAFT_SECTIONS[payload.style]])
    doc = store.create_document(owner, {**payload.model_dump(exclude={"item_ids"}), "sources": sources, "content": {"sections": sections}})
    return _present(doc)


@router.get("/documents/{doc_id}", response_model=WriteDocument)
def get_document(doc_id: str, auth: AuthContext = Depends(get_auth_context)) -> WriteDocument:
    owner = _owner(auth)
    return _present(_guard(lambda: store.get_document(owner, doc_id)))


@router.patch("/documents/{doc_id}", response_model=WriteDocument)
def update_document(doc_id: str, payload: WriteDocumentUpdate, auth: AuthContext = Depends(get_auth_context)) -> WriteDocument:
    owner = _owner(auth)
    doc = _guard(lambda: store.get_document(owner, doc_id))
    changes = payload.model_dump(exclude_unset=True, exclude={"sections"})
    if payload.sections is not None:
        sections = []
        previous = {section["id"]: section for section in doc["content"].get("sections", [])}
        for section in payload.sections:
            data = section.model_dump()
            old = previous.get(section.id)
            if old and old.get("text") != data["text"] and data["status"] == "generated":
                data["status"] = "edited"
            data["unsupported"] = grounding.unsupported_sentences(data["text"], doc["sources"]) if data["text"].strip() else []
            sections.append(data)
        changes["content"] = {**doc["content"], "sections": sections}
    return _present(store.update_document(owner, doc_id, changes))


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str, auth: AuthContext = Depends(get_auth_context)) -> Response:
    owner = _owner(auth)
    _guard(lambda: store.delete_document(owner, doc_id))
    return Response(status_code=204)


@router.post("/documents/{doc_id}/sources", response_model=WriteDocument)
def add_sources(doc_id: str, payload: WriteSourcesAdd, auth: AuthContext = Depends(get_auth_context)) -> WriteDocument:
    """Sources are append-only so existing [n] markers keep pointing at the same paper."""
    owner = _owner(auth)
    doc = _guard(lambda: store.get_document(owner, doc_id))
    present = {source["item_id"] for source in doc["sources"] if source}
    added = [source for source in _library_sources(owner, payload.item_ids, None) if source["item_id"] not in present]
    return _present(store.update_document(owner, doc_id, {"sources": [*doc["sources"], *added]}))


@router.delete("/documents/{doc_id}/sources/{number}", response_model=WriteDocument)
def remove_source(doc_id: str, number: int, auth: AuthContext = Depends(get_auth_context)) -> WriteDocument:
    owner = _owner(auth)
    doc = _guard(lambda: store.get_document(owner, doc_id))
    if not 1 <= number <= len(doc["sources"]):
        raise NOT_FOUND
    sources = list(doc["sources"])
    sources[number - 1] = None
    sections = [{**section, "unsupported": grounding.unsupported_sentences(section.get("text", ""), sources) if section.get("text") else []} for section in doc["content"].get("sections", [])]
    return _present(store.update_document(owner, doc_id, {"sources": sources, "content": {**doc["content"], "sections": sections}}))


@router.post("/documents/{doc_id}/outline", response_model=WriteDocument)
def rebuild_outline(doc_id: str, payload: WriteOutlineRequest, auth: AuthContext = Depends(get_auth_context)) -> WriteDocument:
    """New outline for another review style. Sections that keep their heading keep their text."""
    owner = _owner(auth)
    doc = _guard(lambda: store.get_document(owner, doc_id))
    if doc["kind"] != "review":
        raise HTTPException(status_code=422, detail={"code": "not_a_review"})
    store.save_version(owner, doc_id, "Before new outline")
    kept = {section["heading"].casefold(): section for section in doc["content"].get("sections", []) if section.get("text")}
    sections = []
    plan = grounding.outline_from_themes(doc["sources"], [theme.model_dump() for theme in payload.themes]) if payload.themes else grounding.outline(doc["sources"], payload.style)
    for section in _sections_from_outline(plan):
        old = kept.get(section["heading"].casefold())
        sections.append({**section, **({"id": old["id"], "text": old["text"], "status": old["status"], "unsupported": old.get("unsupported", [])} if old else {})})
    return _present(store.update_document(owner, doc_id, {"style": payload.style, "content": {**doc["content"], "sections": sections}}))


@router.get("/documents/{doc_id}/themes")
def document_themes(doc_id: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    """Candidate themes for the review (shared tasks, methods, datasets) with whether their results agree."""
    owner = _owner(auth)
    doc = _guard(lambda: store.get_document(owner, doc_id))
    return {"themes": grounding.themes(doc["sources"])}


@router.post("/documents/{doc_id}/sections/{section_id}/write", response_model=WriteDocument)
async def write_section(doc_id: str, section_id: str, payload: WriteSectionRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> WriteDocument:
    owner = _owner(auth)
    doc = await asyncio.to_thread(lambda: _guard(lambda: store.get_document(owner, doc_id)))
    sections = doc["content"].get("sections", [])
    section = next((item for item in sections if item["id"] == section_id), None)
    if not section:
        raise NOT_FOUND
    if not any(doc["sources"]):
        raise HTTPException(status_code=422, detail={"code": "no_sources"})
    if section.get("text"):
        await asyncio.to_thread(store.save_version, owner, doc_id, f"Before rewriting: {section['heading']}"[:120])
    try:
        text, _ = await _with_credits(auth, request, "summary", lambda: grounding.write_section(
            heading=section["heading"], purpose=section.get("purpose", "section"), sources=doc["sources"], numbers=section.get("papers") or [],
            style=doc["style"], language=doc["language"], instruction=payload.instruction, doc_title=doc["title"], outline_headings=[item["heading"] for item in sections],
        ))
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=503, detail={"code": "ai_unavailable"}) from error
    updated = [{**item, "text": text, "status": "generated", "unsupported": grounding.unsupported_sentences(text, doc["sources"])} if item["id"] == section_id else item for item in sections]
    return _present(await asyncio.to_thread(store.update_document, owner, doc_id, {"content": {**doc["content"], "sections": updated}}))


@router.get("/documents/{doc_id}/check")
def check_document(doc_id: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    return exporter.consistency(_guard(lambda: store.get_document(owner, doc_id)))


@router.get("/documents/{doc_id}/versions")
def list_versions(doc_id: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    return {"versions": _guard(lambda: store.list_versions(owner, doc_id))}


@router.post("/documents/{doc_id}/versions")
def save_version(doc_id: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    return _guard(lambda: store.save_version(owner, doc_id, "Saved version"))


@router.post("/documents/{doc_id}/versions/{version_id}/restore", response_model=WriteDocument)
def restore_version(doc_id: str, version_id: str, auth: AuthContext = Depends(get_auth_context)) -> WriteDocument:
    owner = _owner(auth)
    return _present(_guard(lambda: store.restore_version(owner, doc_id, version_id)))


@router.post("/documents/{doc_id}/export")
def export_document(doc_id: str, payload: WriteExportRequest, auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    doc = _guard(lambda: store.get_document(owner, doc_id))
    slug = "".join(character if character.isalnum() else "-" for character in doc["title"].lower())[:60].strip("-") or "resora-document"
    if payload.format == "docx":
        data = exporter.to_docx(doc, rtl=payload.rtl, references_label=payload.references_label)
        return {"filename": f"{slug}.docx", "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "base64": base64.b64encode(data).decode()}
    if payload.format == "latex":
        tex, bib = exporter.to_latex(doc)
        return {"filename": f"{slug}.tex", "mime": "application/x-tex", "content": tex, "bib": bib, "bib_filename": "references.bib"}
    if payload.format == "html":
        return {"filename": f"{slug}.html", "mime": "text/html", "content": exporter.to_html(doc, rtl=payload.rtl, language=doc["language"], labels={"references": payload.references_label})}
    return {"filename": f"{slug}.md", "mime": "text/markdown", "content": exporter.to_markdown(doc)}


# --------------------------------------------------------------------------- screening


def _papers_from_import(content: str, filename: str | None) -> list[dict]:
    fmt = C.detect_format(content, filename)
    if fmt == "ids":
        raise HTTPException(status_code=422, detail={"code": "unreadable_file"})
    try:
        return C.parse(content, fmt)
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(status_code=422, detail={"code": "unreadable_file"}) from error


@router.get("/screenings")
def list_screenings(auth: AuthContext = Depends(get_auth_context)) -> dict:
    return {"screenings": store.list_screenings(_owner(auth))}


@router.post("/screenings")
def create_screening(payload: ScreeningCreate, auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    screening = store.create_screening(owner, payload.name, payload.project_id, payload.criteria)
    papers = [{**source, "library_item_id": source["item_id"]} for source in _library_sources(owner, payload.item_ids, payload.project_id)]
    if papers:
        store.add_records(owner, screening["id"], papers)
    return store.get_screening(owner, screening["id"])


@router.get("/screenings/{screening_id}")
def get_screening(screening_id: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    return _guard(lambda: store.get_screening(owner, screening_id))


@router.patch("/screenings/{screening_id}")
def update_screening(screening_id: str, payload: ScreeningUpdate, auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    return _guard(lambda: store.update_screening(owner, screening_id, payload.name, payload.criteria))


@router.delete("/screenings/{screening_id}", status_code=204)
def delete_screening(screening_id: str, auth: AuthContext = Depends(get_auth_context)) -> Response:
    owner = _owner(auth)
    _guard(lambda: store.delete_screening(owner, screening_id))
    return Response(status_code=204)


@router.post("/screenings/{screening_id}/records")
def import_records(screening_id: str, payload: ScreeningImport, auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    papers = [{**source, "library_item_id": source["item_id"]} for source in _library_sources(owner, payload.item_ids, None)]
    if payload.content:
        papers += _papers_from_import(payload.content, payload.filename)
    if not papers:
        raise HTTPException(status_code=422, detail={"code": "nothing_to_import"})
    result = _guard(lambda: store.add_records(owner, screening_id, papers))
    return {**result, "screening": store.get_screening(owner, screening_id)}


@router.patch("/screenings/{screening_id}/records/{record_id}")
def decide(screening_id: str, record_id: str, payload: ScreeningDecision, auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    record = _guard(lambda: store.decide(owner, screening_id, record_id, payload.model_dump(exclude_unset=True)))
    return {"record": record, "prisma": store.get_screening(owner, screening_id)["prisma"]}


@router.post("/screenings/{screening_id}/to-library")
def included_to_library(screening_id: str, payload: ScreeningToLibrary, auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner = _owner(auth)
    screening = _guard(lambda: store.get_screening(owner, screening_id))
    included = [record for record in screening["records"] if not record["duplicate_of"] and record["ta_decision"] == "include" and record["ft_decision"] == "include"]
    if not included:
        raise HTTPException(status_code=422, detail={"code": "nothing_included"})
    papers = [{key: record.get(key) for key in ("title", "authors", "year", "venue", "doi", "abstract")} for record in included]
    items, existing = _guard(lambda: library.add_items(owner, papers, source="import", list_id=payload.project_id or screening["project_id"]))
    return {"saved": len(items), "already_saved": len(set(existing))}


# --------------------------------------------------------------------------- claims


@router.post("/claims", response_model=ClaimCheckResponse)
async def check_claims(payload: ClaimCheckRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> ClaimCheckResponse:
    owner = _owner(auth)
    if payload.document_id:
        doc = await asyncio.to_thread(lambda: _guard(lambda: store.get_document(owner, payload.document_id)))
        sources = doc["sources"]
    else:
        sources = await asyncio.to_thread(lambda: _library_sources(owner, payload.item_ids, payload.project_id))
        if not sources and not payload.item_ids and not payload.project_id:
            sources = [_source(item) for item in await asyncio.to_thread(library.list_items, owner)][:300]
    if not any(sources):
        raise HTTPException(status_code=422, detail={"code": "no_sources"})
    claims = grounding.split_claims(payload.text)
    if not claims:
        raise HTTPException(status_code=422, detail={"code": "no_claims"})
    mode, used = "ai", 0
    try:
        results, used = await _with_credits(auth, request, "chat", lambda: grounding.ai_verdicts(claims, sources, payload.language))
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - labelled keyword fallback
        results, mode = grounding.keyword_verdicts(claims, sources), "keywords"
    listed = [{"n": number, "item_id": source.get("item_id"), "title": source.get("title"), "year": source.get("year"), "authors": (source.get("authors") or [])[:3]} for number, source in enumerate(sources, start=1) if source]
    return ClaimCheckResponse(mode=mode, claims=results, sources=listed, credits_used=used)
