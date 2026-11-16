"""Listen: clean listening scripts, voices, neural speech (credits per chunk), resume positions and the queue."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import AuthContext, get_auth_context
from app.core.config import settings
from app.services.listen import store
from app.services.listen.script import ScriptOptions, build_script, script_from_texts
from app.services.listen.tts import TTSUnavailable, get_tts_router
from app.services.reader.store import DocumentNotFound, get_reader_store

router = APIRouter()


def _user_key(auth: AuthContext, request: Request) -> str:
    """Positions and the queue follow the account (any device); guests are kept per network address."""
    production = settings.deployment_stage.lower() == "production"
    if auth.user_id and auth.user_id != "anonymous" and (auth.verified or not production):
        return f"user:{auth.user_id}"
    return f"guest:{request.client.host if request.client else 'unknown'}"


def _reader_key(auth: AuthContext, request: Request) -> str:
    """Same identity the Reader uses for private uploads."""
    if auth.verified and auth.user_id:
        return f"user:{auth.user_id}"
    return f"guest:{request.client.host if request.client else 'unknown'}"


def _guard(call):
    try:
        return call()
    except store.ListenError as error:
        raise HTTPException(status_code=error.status, detail={"code": error.code}) from error


class ScriptRequest(BaseModel):
    document_id: str | None = Field(default=None, max_length=200)
    texts: list[str] | None = Field(default=None, max_length=2000)
    kind: str = Field(default="paper", pattern="^(paper|summary|key_points|section|text|answer|translation)$")
    language: str | None = Field(default=None, max_length=16)
    title: str | None = Field(default=None, max_length=400)
    authors: list[str] | None = Field(default=None, max_length=50)
    translated_from: str | None = Field(default=None, max_length=16)
    read_references: bool = False
    read_citations: bool = False
    read_captions: bool = True


@router.post("/script")
async def script(payload: ScriptRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> dict:
    options = ScriptOptions(read_references=payload.read_references, read_citations=payload.read_citations, read_captions=payload.read_captions)
    if payload.document_id and not payload.texts:
        reader = get_reader_store()
        try:
            document = await asyncio.to_thread(reader.get, payload.document_id, _reader_key(auth, request))
            pages = await asyncio.to_thread(reader.pages, payload.document_id, _reader_key(auth, request))
        except DocumentNotFound as error:
            raise HTTPException(status_code=404, detail={"code": "not_found"}) from error
        result = await asyncio.to_thread(lambda: build_script(pages, language=payload.language, title=document.title, authors=document.authors, options=options, translated_from=payload.translated_from))
    elif payload.texts:
        texts = [text[:20000] for text in payload.texts if text and text.strip()]
        if sum(len(text) for text in texts) > 1_500_000:
            raise HTTPException(status_code=413, detail={"code": "too_long"})
        if payload.kind in {"paper", "translation"}:
            result = await asyncio.to_thread(lambda: build_script(texts, language=payload.language, title=payload.title, authors=payload.authors, options=options, translated_from=payload.translated_from))
        else:
            result = await asyncio.to_thread(lambda: script_from_texts(texts, language=payload.language, title=payload.title))
    else:
        raise HTTPException(status_code=422, detail={"code": "nothing_to_read"})
    result["kind"] = payload.kind
    return result


@router.get("/voices")
async def voices(language: str = "en") -> dict:
    return get_tts_router().voices(language[:16])


class EstimateRequest(BaseModel):
    characters: int = Field(ge=0, le=5_000_000)
    language: str = Field(default="en", max_length=16)
    voice: str = Field(default="browser", max_length=80)


@router.post("/estimate")
async def estimate(payload: EstimateRequest) -> dict:
    return store.estimate(payload.characters, payload.language, "neural" if payload.voice.startswith("neural:") else "browser")


class SessionRequest(BaseModel):
    voice: str = Field(max_length=80)
    language: str = Field(default="en", max_length=16)
    characters: int = Field(ge=1, le=5_000_000)


@router.post("/sessions", status_code=201)
async def start(payload: SessionRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> dict:
    if payload.voice.startswith("neural:"):
        listing = get_tts_router().voices(payload.language)
        if not any(voice["id"] == payload.voice for voice in listing["voices"]):
            raise HTTPException(status_code=422, detail={"code": "voice_unavailable"})
    return await asyncio.to_thread(lambda: _guard(lambda: store.start_session(_user_key(auth, request), voice=payload.voice, language=payload.language, characters=payload.characters)))


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1200)


@router.post("/sessions/{session_id}/speak")
async def speak(session_id: str, payload: SpeakRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> Response:
    key = _user_key(auth, request)
    row = await asyncio.to_thread(lambda: _guard(lambda: store.session(key, session_id)))
    if not row["voice"].startswith("neural:"):
        raise HTTPException(status_code=422, detail={"code": "browser_voice"})
    await asyncio.to_thread(lambda: _guard(lambda: store.record_chunk(key, session_id, len(payload.text))))
    try:
        result = await asyncio.to_thread(get_tts_router().synthesize, payload.text, voice_id=row["voice"], language=row["language"])
    except TTSUnavailable as error:
        # The player falls back to the browser voice for the rest of the listen; the chunk is not charged.
        await asyncio.to_thread(lambda: store.record_chunk(key, session_id, -len(payload.text)))
        raise HTTPException(status_code=503, detail={"code": "voice_unavailable", "reason": str(error)}) from error
    return Response(content=result.audio, media_type=result.content_type, headers={"Cache-Control": "private, max-age=86400", "X-Resora-Cached": "1" if result.cached else "0"})


@router.post("/sessions/{session_id}/finish")
async def finish(session_id: str, request: Request, auth: AuthContext = Depends(get_auth_context)) -> dict:
    return await asyncio.to_thread(lambda: _guard(lambda: store.finish_session(_user_key(auth, request), session_id)))


class ProgressRequest(BaseModel):
    item_id: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="paper", max_length=20)
    title: str = Field(default="", max_length=300)
    language: str = Field(default="en", max_length=16)
    section: int = Field(default=0, ge=0, le=100000)
    sentence: int = Field(default=0, ge=0, le=1000000)
    total_sections: int = Field(default=0, ge=0, le=100000)
    percent: float = Field(default=0, ge=0, le=1)
    voice: str | None = Field(default=None, max_length=80)
    rate: float = Field(default=1, ge=0.5, le=2)


@router.get("/progress")
async def get_progress(request: Request, item_id: str | None = None, auth: AuthContext = Depends(get_auth_context)) -> dict:
    return {"items": await asyncio.to_thread(store.progress, _user_key(auth, request), item_id)}


@router.put("/progress")
async def put_progress(payload: ProgressRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> dict:
    return await asyncio.to_thread(store.save_progress, _user_key(auth, request), payload.model_dump())


class QueueItem(BaseModel):
    item_id: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="paper", max_length=20)
    title: str = Field(default="", max_length=300)
    payload: dict = Field(default_factory=dict)


@router.get("/queue")
async def get_queue(request: Request, auth: AuthContext = Depends(get_auth_context)) -> dict:
    return {"items": await asyncio.to_thread(store.queue, _user_key(auth, request))}


@router.post("/queue", status_code=201)
async def add_queue(payload: QueueItem, request: Request, auth: AuthContext = Depends(get_auth_context)) -> dict:
    return {"items": await asyncio.to_thread(lambda: _guard(lambda: store.enqueue(_user_key(auth, request), payload.model_dump())))}


@router.delete("/queue/{entry_id}")
async def remove_queue(entry_id: str, request: Request, auth: AuthContext = Depends(get_auth_context)) -> dict:
    return {"items": await asyncio.to_thread(store.dequeue, _user_key(auth, request), entry_id)}


class ReorderRequest(BaseModel):
    ids: list[str] = Field(max_length=200)


@router.post("/queue/reorder")
async def reorder_queue(payload: ReorderRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> dict:
    return {"items": await asyncio.to_thread(store.reorder, _user_key(auth, request), payload.ids)}
