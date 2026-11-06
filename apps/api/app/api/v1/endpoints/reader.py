"""Reader API: open a paper from search, a link or an upload; read pages; summary, chat and translation.

Credits (Master Prompt Part 9): summary 2, chat message 1, translation 1 per 5 pages. Cached results cost 0.
Failed AI work is refunded. Errors never expose internal details or provider names.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import AuthContext, get_auth_context
from app.schemas.reader import (
    AskRequest,
    ReaderAnswer,
    ReaderDocument,
    ReaderOpenRequest,
    ReaderPage,
    ReaderPagesResponse,
    ReaderSummary,
    SummaryRequest,
    TranslateRequest,
    TranslateResponse,
)
from app.services.credits.service import CreditLimitReached, get_credit_service
from app.services.reader.intelligence import ReaderAIUnavailable
from app.services.reader.service import MAX_UPLOAD_BYTES, DocumentNotFound, ReaderInputError, get_reader_service

router = APIRouter()

INPUT_ERRORS = {
    "too_large": (413, "This PDF is too large."),
    "not_pdf": (415, "Please choose a PDF file."),
    "unreadable": (422, "This PDF could not be read."),
    "nothing_to_open": (422, "Nothing to open."),
    "no_full_text": (404, "No open-access full text was found for this paper."),
    "bad_pages": (422, "Those pages are not in this document."),
}


def _viewer_key(auth: AuthContext, request: Request) -> str:
    """Signed-in users own their uploads; guests are separated by network address."""
    if getattr(auth, "verified", False) and auth.user_id:
        return f"user:{auth.user_id}"
    host = request.client.host if request.client else "unknown"
    return f"guest:{host}"


def _plan(auth: AuthContext) -> str:
    return str(getattr(auth, "plan", None) or "free")


def _limit(error: CreditLimitReached) -> HTTPException:
    return HTTPException(
        status_code=402,
        detail={"code": "limit_reached", "scope": error.scope, "resets_at": datetime.fromtimestamp(error.resets_at, tz=timezone.utc).isoformat()},
    )


def _input_error(error: ReaderInputError) -> HTTPException:
    status, message = INPUT_ERRORS.get(str(error), (422, "This document could not be opened."))
    return HTTPException(status_code=status, detail={"code": str(error), "message": message})


NOT_FOUND = HTTPException(status_code=404, detail={"code": "not_found", "message": "Document not found."})
AI_UNAVAILABLE = HTTPException(status_code=503, detail={"code": "unavailable", "message": "This is not available right now. Please try again shortly."})


@router.post("/upload", response_model=ReaderDocument)
async def upload_document(request: Request, file: UploadFile = File(...), auth: AuthContext = Depends(get_auth_context)) -> ReaderDocument:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        return await get_reader_service().upload(data, file.filename or "", _viewer_key(auth, request))
    except ReaderInputError as error:
        raise _input_error(error) from error


@router.post("/open", response_model=ReaderDocument)
async def open_document(payload: ReaderOpenRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> ReaderDocument:
    try:
        return await get_reader_service().open_paper(payload.paper, payload.link, _viewer_key(auth, request))
    except ReaderInputError as error:
        raise _input_error(error) from error


@router.get("/{doc_id}", response_model=ReaderDocument)
async def get_document(doc_id: str, request: Request, auth: AuthContext = Depends(get_auth_context)) -> ReaderDocument:
    try:
        return get_reader_service().document(doc_id, _viewer_key(auth, request))
    except DocumentNotFound as error:
        raise NOT_FOUND from error


@router.get("/{doc_id}/pdf")
async def get_pdf(doc_id: str, request: Request, auth: AuthContext = Depends(get_auth_context)) -> FileResponse:
    try:
        path = get_reader_service().store.pdf_path(doc_id, _viewer_key(auth, request))
    except DocumentNotFound as error:
        raise NOT_FOUND from error
    return FileResponse(path, media_type="application/pdf", headers={"Cache-Control": "private, max-age=3600", "Content-Disposition": "inline"})


@router.get("/{doc_id}/pages", response_model=ReaderPagesResponse)
async def get_pages(
    doc_id: str,
    request: Request,
    start: int = Query(1, ge=1),
    end: int = Query(400, ge=1),
    auth: AuthContext = Depends(get_auth_context),
) -> ReaderPagesResponse:
    try:
        pages = get_reader_service().pages(doc_id, _viewer_key(auth, request), start, end)
    except DocumentNotFound as error:
        raise NOT_FOUND from error
    return ReaderPagesResponse(pages=[ReaderPage(page=number, text=text) for number, text in pages])


@router.post("/{doc_id}/summary", response_model=ReaderSummary)
async def summarize(doc_id: str, payload: SummaryRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> ReaderSummary:
    service = get_reader_service()
    viewer = _viewer_key(auth, request)
    try:
        cached = service.cached_summary(doc_id, viewer, payload.level, payload.language)
    except DocumentNotFound as error:
        raise NOT_FOUND from error
    if cached:
        return cached.model_copy(update={"credits_used": 0})
    credits = get_credit_service()
    try:
        reservation = credits.reserve(viewer, "summary", plan=_plan(auth))
    except CreditLimitReached as error:
        raise _limit(error) from error
    try:
        summary = await asyncio.to_thread(service.summarize, doc_id, viewer, payload.level, payload.language)
    except DocumentNotFound as error:
        credits.refund(reservation)
        raise NOT_FOUND from error
    except Exception as error:  # noqa: BLE001
        credits.refund(reservation)
        raise AI_UNAVAILABLE from error
    used = 0 if summary.basic else credits.cost("summary")
    credits.commit(reservation, used)
    return summary.model_copy(update={"credits_used": used})


@router.post("/{doc_id}/ask", response_model=ReaderAnswer)
async def ask(doc_id: str, payload: AskRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> ReaderAnswer:
    service = get_reader_service()
    viewer = _viewer_key(auth, request)
    try:
        service.document(doc_id, viewer)
    except DocumentNotFound as error:
        raise NOT_FOUND from error
    credits = get_credit_service()
    try:
        reservation = credits.reserve(viewer, "chat", plan=_plan(auth))
    except CreditLimitReached as error:
        raise _limit(error) from error
    try:
        answer = await asyncio.to_thread(service.ask, doc_id, viewer, payload.question, payload.language)
    except (ReaderAIUnavailable, Exception) as error:  # noqa: BLE001
        credits.refund(reservation)
        raise AI_UNAVAILABLE from error
    used = credits.cost("chat")
    credits.commit(reservation, used)
    return answer.model_copy(update={"credits_used": used})


@router.post("/{doc_id}/translate", response_model=TranslateResponse)
async def translate(doc_id: str, payload: TranslateRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> TranslateResponse:
    service = get_reader_service()
    viewer = _viewer_key(auth, request)
    try:
        cached = service.cached_translation(doc_id, viewer, payload.pages, payload.language)
    except DocumentNotFound as error:
        raise NOT_FOUND from error
    if cached:
        return cached
    credits = get_credit_service()
    try:
        reservation = credits.reserve(viewer, "translate_pages", amount=max(1, credits.cost("translate_pages")), plan=_plan(auth))
    except CreditLimitReached as error:
        raise _limit(error) from error
    try:
        result = await asyncio.to_thread(service.translate, doc_id, viewer, payload.pages, payload.language)
    except ReaderInputError as error:
        credits.refund(reservation)
        raise _input_error(error) from error
    except Exception as error:  # noqa: BLE001
        credits.refund(reservation)
        raise AI_UNAVAILABLE from error
    used = max(1, credits.cost("translate_pages"))
    credits.commit(reservation, used)
    return result.model_copy(update={"credits_used": used})
