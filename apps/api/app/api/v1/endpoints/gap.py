"""Gaps API. /analyze is the legacy report used by the gap agent (unchanged). Everything else powers the Gaps tab:
evidence-levelled signals with the papers behind every count, trends, people, datasets, consensus and AI hypotheses."""

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import AuthContext, get_auth_context
from app.core.config import settings
from app.schemas.gap import (
    GapAnalyzeRequest,
    GapAnalyzeResponse,
    GapConsensusRequest,
    GapConsensusResponse,
    GapHypothesesRequest,
    GapHypothesesResponse,
    GapIdeaRequest,
    GapRecommendRequest,
    GapRecommendResponse,
    GapReportRequest,
    GapReportResponse,
    GapStateRequest,
)
from app.services.gap.detector import GapDetectionService
from app.services.gaps import ai as gap_ai
from app.services.gaps.analysis import Paper, analyze
from app.services.gaps.recommend import recommend
from app.services.gaps.store import GapStateStore
from app.services.library.store import LibraryNotFound, LibraryStore

router = APIRouter()
service = GapDetectionService()
states = GapStateStore()
library = LibraryStore()


@router.post("/analyze", response_model=GapReportResponse)
async def analyze_gap(payload: GapReportRequest) -> GapReportResponse:
    return service.analyze(payload)


def _owner(auth: AuthContext) -> str:
    if (settings.deployment_stage.lower() == "production" and not auth.verified) or not auth.user_id or auth.user_id == "anonymous":
        raise HTTPException(status_code=401, detail={"code": "sign_in_required"})
    return auth.user_id


def _papers(items) -> list[Paper]:
    unique: dict[str, Paper] = {}
    for item in items:
        unique.setdefault(item.id, Paper(**item.model_dump()))
    return list(unique.values())


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


@router.post("/signals", response_model=GapAnalyzeResponse)
def gap_signals(payload: GapAnalyzeRequest, auth: AuthContext = Depends(get_auth_context)) -> GapAnalyzeResponse:
    owner = _owner(auth)
    result = analyze(_papers(payload.papers), current_year=payload.current_year or datetime.now(UTC).year)
    saved = {row["signal_id"]: row["state"] for row in states.states(owner, payload.scope.key)}
    return GapAnalyzeResponse(scope_key=payload.scope.key, states=saved, **result)


@router.get("/states")
def list_states(scope_key: str | None = None, auth: AuthContext = Depends(get_auth_context)) -> dict:
    return {"states": states.states(_owner(auth), scope_key)}


@router.put("/states/{signal_id}", status_code=204)
def set_state(signal_id: str, payload: GapStateRequest, auth: AuthContext = Depends(get_auth_context)) -> None:
    states.set_state(_owner(auth), payload.scope_key, signal_id[:120], payload.state, payload.snapshot)


@router.post("/states/{signal_id}/idea")
def signal_to_idea(signal_id: str, payload: GapIdeaRequest, auth: AuthContext = Depends(get_auth_context)) -> dict:
    """Turn a signal into an idea in the owner's Library (in the project when the scope is a project)."""
    owner = _owner(auth)
    try:
        note = library.create_note(owner, {"kind": "idea", "title": payload.title, "body": payload.body, "project_id": payload.project_id})
    except LibraryNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "not_found"}) from error
    states.set_state(owner, payload.scope_key, signal_id[:120], "idea", {**payload.snapshot, "idea_id": note["id"]})
    return {"idea_id": note["id"]}


@router.post("/consensus", response_model=GapConsensusResponse)
async def consensus(payload: GapConsensusRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> GapConsensusResponse:
    _owner(auth)
    papers = _papers(payload.papers)
    mode, used = "ai", 0
    try:
        rows, used = await _with_credits(auth, request, "summary", lambda: gap_ai.ai_consensus(payload.question, papers, payload.language))
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - transparent keyword fallback, clearly labelled in the UI
        rows, mode = gap_ai.keyword_consensus(payload.question, papers), "keywords"
    counts = {stance: sum(1 for row in rows if row["stance"] == stance) for stance in gap_ai.STANCES}
    return GapConsensusResponse(mode=mode, rows=rows, counts=counts, credits_used=used)


@router.post("/hypotheses", response_model=GapHypothesesResponse)
async def hypotheses(payload: GapHypothesesRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> GapHypothesesResponse:
    _owner(auth)
    papers = _papers(payload.papers)
    try:
        items, used = await _with_credits(auth, request, "summary", lambda: gap_ai.ai_hypotheses(payload.focus, papers, payload.signals, payload.language))
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=503, detail={"code": "ai_unavailable"}) from error
    return GapHypothesesResponse(hypotheses=items, credits_used=used)


@router.post("/recommendations", response_model=GapRecommendResponse)
async def recommendations(payload: GapRecommendRequest, auth: AuthContext = Depends(get_auth_context)) -> GapRecommendResponse:
    """Papers worth reading next, each with one checkable reason. Free (no AI, no credits)."""
    _owner(auth)
    year = payload.current_year or datetime.now(UTC).year
    notes = [note[:2000] for note in payload.notes]
    rows = await asyncio.to_thread(recommend, _papers(payload.saved), _papers(payload.candidates), notes=notes, current_year=year, limit=payload.limit)
    return GapRecommendResponse(recommendations=rows)
