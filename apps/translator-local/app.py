from __future__ import annotations

import json
import os
import re
from pathlib import Path
from threading import RLock
from typing import Any

from fastapi import FastAPI, HTTPException
from langdetect import DetectorFactory, detect
from pydantic import BaseModel, Field

_FILE_PARENTS = Path(__file__).resolve().parents
_DEFAULT_ROOT = _FILE_PARENTS[2] / "models" if len(_FILE_PARENTS) > 2 else Path("/models")
ROOT = Path(os.getenv("RESORA_MODELS_DIR", str(_DEFAULT_ROOT)))
os.environ.setdefault("RESORA_MODELS_DIR", str(ROOT))
os.environ.setdefault("XDG_DATA_HOME", str(ROOT))
from engine_manager import APP_LANGUAGES, M2M_CODES, engine_status, license_inventory, loaded_model_names, translate_batch_with_engine

MAX_SEGMENT_CHARS = 12_000
MAX_BATCH_SEGMENTS = 24
TRANSLATION_LOCK = RLock()
ALIASES = {"zh": "zh-Hans", "zh-cn": "zh-Hans", "zh-hans": "zh-Hans", "zh-tw": "zh-Hant", "zh-hant": "zh-Hant", "pt": "pt-BR", "pt-br": "pt-BR", "pt-pt": "pt-PT", "pa": "pa-Arab", "pa-arab": "pa-Arab", "iw": "he"}
PROTECTED_TOKEN = re.compile(r"RESORATOKENX\d+XEND", re.IGNORECASE)
DetectorFactory.seed = 0
app = FastAPI(title="Resora Local Translator", docs_url=None, redoc_url=None)


class TranslationRequest(BaseModel):
    segments: list[str] = Field(min_length=1, max_length=MAX_BATCH_SEGMENTS)
    source_language: str = "auto"
    target_language: str


class TranslationResponse(BaseModel):
    translations: list[str]
    provider: str = "translator_local"
    engines_used: list[str]
    source_language: str
    target_language: str


def code(value: str) -> str:
    return ALIASES.get(value.strip().casefold(), value.strip())


def _engine_order(target: str) -> list[str]:
    default = [part.strip().casefold() for part in os.getenv("LOCAL_TRANSLATION_ENGINE_ORDER", "argos,m2m100,opus_mt").split(",") if part.strip()]
    try:
        routes = json.loads(os.getenv("LOCAL_TRANSLATION_LANGUAGE_ROUTES", "{}"))
        configured = routes.get(target) if isinstance(routes, dict) else None
    except (json.JSONDecodeError, TypeError):
        configured = None
    if not isinstance(configured, list):
        return default
    allowed = {"argos", "m2m100", "opus_mt"}
    route = [str(engine).strip().casefold() for engine in configured if str(engine).strip().casefold() in allowed]
    return route or default


def _tokens_valid(inputs: list[str], outputs: list[str]) -> bool:
    if len(inputs) != len(outputs):
        return False
    for original, translated in zip(inputs, outputs):
        expected = PROTECTED_TOKEN.findall(original)
        actual = PROTECTED_TOKEN.findall(translated)
        if sorted(token.casefold() for token in expected) != sorted(token.casefold() for token in actual):
            return False
    return True


def _translate_preserving_tokens(engine: str, texts: list[str], source: str, target: str) -> list[str]:
    layouts: list[list[tuple[str, str]]] = []
    fragments: list[str] = []
    for text in texts:
        layout: list[tuple[str, str]] = []
        cursor = 0
        for match in PROTECTED_TOKEN.finditer(text):
            fragment = text[cursor:match.start()]
            if fragment:
                layout.append(("fragment", str(len(fragments))))
                fragments.append(fragment)
            layout.append(("token", match.group(0)))
            cursor = match.end()
        tail = text[cursor:]
        if tail:
            layout.append(("fragment", str(len(fragments))))
            fragments.append(tail)
        layouts.append(layout)
    translated = translate_batch_with_engine(engine, fragments, source, target) if fragments else []
    if len(translated) != len(fragments):
        raise ValueError("Engine returned an incomplete protected-text batch")
    if any(not isinstance(item, str) or not item.strip() for item in translated):
        raise ValueError("Engine returned an empty text fragment")
    return ["".join(value if kind == "token" else translated[int(value)] for kind, value in layout) for layout in layouts]


def _detect_source(text: str) -> str:
    try:
        detected = detect(text)
    except Exception:
        return "en"
    return code({"zh-cn": "zh-Hans", "zh-tw": "zh-Hant", "pt": "pt-BR", "iw": "he"}.get(detected, detected))


@app.get("/health")
def health() -> dict[str, Any]:
    engines = engine_status()
    available = any(item["status"] == "available" for item in engines.values())
    routes = {target: {"order": _engine_order(target), "available": [engine for engine in _engine_order(target) if engines.get(engine, {}).get("status") == "available"]} for target in sorted(APP_LANGUAGES)}
    return {"status": "ready" if available else "degraded", "provider": "translator_local", "engines": engines, "language_routes": routes, "loaded_models": loaded_model_names()}


@app.get("/languages")
def languages() -> dict[str, Any]:
    engines = engine_status()
    available = {name: info for name, info in engines.items() if info["status"] == "available"}
    return {
        "supported_targets": sorted(APP_LANGUAGES),
        "installed_languages": sorted({language for info in available.values() for language in info.get("languages", [])}),
        "supported_pairs": sorted({pair for info in available.values() for pair in info.get("pairs", [])}),
        "engines": engines,
    }


@app.get("/licenses")
def licenses() -> dict[str, Any]:
    return license_inventory()


@app.post("/translate", response_model=TranslationResponse)
def translate_batch(payload: TranslationRequest) -> TranslationResponse:
    if any(not segment.strip() or len(segment) > MAX_SEGMENT_CHARS for segment in payload.segments):
        raise HTTPException(status_code=413, detail="Segments must contain 1 to 12,000 characters")
    target = code(payload.target_language)
    source = code(payload.source_language) if payload.source_language != "auto" else "auto"
    if target not in APP_LANGUAGES or (source != "auto" and source not in APP_LANGUAGES):
        raise HTTPException(status_code=422, detail="Unsupported translation language")
    sources = [(_detect_source(text) if source == "auto" else source) for text in payload.segments]
    results: list[str | None] = [None] * len(payload.segments)
    engines_used: list[str | None] = [None] * len(payload.segments)
    groups: dict[str, list[int]] = {}
    for index, segment_source in enumerate(sources):
        if segment_source == target:
            results[index] = payload.segments[index]
            engines_used[index] = "identity"
        else:
            groups.setdefault(segment_source, []).append(index)
    if not groups:
        return TranslationResponse(translations=[str(value) for value in results], engines_used=[str(value) for value in engines_used], source_language=source, target_language=target)
    engines = engine_status()
    tried: list[str] = []
    errors: list[str] = []
    with TRANSLATION_LOCK:
        for segment_source, indices in groups.items():
            texts = [payload.segments[index] for index in indices]
            translated = False
            for engine in _engine_order(target):
                state = engines.get(engine)
                if not state or state.get("status") != "available":
                    continue
                if engine == "opus_mt" and f"{segment_source}->{target}" not in state.get("pairs", []):
                    continue
                tried.append(engine)
                try:
                    outputs = _translate_preserving_tokens(engine, texts, segment_source, target)
                    if any(not isinstance(item, str) or not item.strip() for item in outputs):
                        raise ValueError("Engine returned an empty translation")
                    if not _tokens_valid(texts, outputs):
                        raise ValueError("Engine changed a protected academic token")
                    for index, output in zip(indices, outputs):
                        results[index] = output
                        engines_used[index] = engine
                    translated = True
                    break
                except Exception as exc:
                    errors.append(f"{engine}:{type(exc).__name__}")
            if not translated:
                raise HTTPException(status_code=503, detail={"message": "Local translation is temporarily unavailable", "engines_tried": tried, "engine_failures": errors})
    return TranslationResponse(translations=[str(value) for value in results], engines_used=[str(value) for value in engines_used], source_language=source, target_language=target)
