"""TTS Router: every spoken word goes through here (same pattern as the AI Router).

Engines, in priority order per language:
  1. Self-hosted neural TTS with a permissive licence — Kokoro-82M (Apache-2.0) served by an OpenAI-compatible
     speech server (e.g. Kokoro-FastAPI) at TTS_KOKORO_URL. User text never leaves your own infrastructure.
  2. Browser speech synthesis (Web Speech API) — free, instant and private; chosen on the device. The router only
     describes it so the player can offer it; no audio is produced on the server.

Deliberately NOT supported (licence or privacy): non-commercial voices (Coqui XTTS, MMS-TTS), unofficial wrappers
of commercial services (edge-tts), GPL components linked into the app, and cloud engines that may train on input.

Voices have friendly names only ("Heart — English (US)"); engine names never reach the interface.
Audio is cached on disk keyed by sha256(engine, voice, language, text), so a public paper read once is free
for everyone afterwards. A language without a voice is reported as such — a wrong-language voice is never used.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

API_ROOT = Path(__file__).resolve().parents[3]

# Kokoro-82M voice registry (voices published with the Apache-2.0 model). Language codes follow Resora's catalog.
KOKORO_VOICES: list[dict[str, str]] = [
    {"id": "af_heart", "name": "Heart", "language": "en", "locale": "en-US", "gender": "female"},
    {"id": "am_michael", "name": "Michael", "language": "en", "locale": "en-US", "gender": "male"},
    {"id": "bf_emma", "name": "Emma", "language": "en", "locale": "en-GB", "gender": "female"},
    {"id": "bm_george", "name": "George", "language": "en", "locale": "en-GB", "gender": "male"},
    {"id": "ef_dora", "name": "Dora", "language": "es", "locale": "es-ES", "gender": "female"},
    {"id": "em_alex", "name": "Alex", "language": "es", "locale": "es-ES", "gender": "male"},
    {"id": "ff_siwis", "name": "Siwis", "language": "fr", "locale": "fr-FR", "gender": "female"},
    {"id": "hf_alpha", "name": "Alpha", "language": "hi", "locale": "hi-IN", "gender": "female"},
    {"id": "hm_omega", "name": "Omega", "language": "hi", "locale": "hi-IN", "gender": "male"},
    {"id": "if_sara", "name": "Sara", "language": "it", "locale": "it-IT", "gender": "female"},
    {"id": "im_nicola", "name": "Nicola", "language": "it", "locale": "it-IT", "gender": "male"},
    {"id": "jf_alpha", "name": "Hana", "language": "ja", "locale": "ja-JP", "gender": "female"},
    {"id": "jm_kumo", "name": "Kumo", "language": "ja", "locale": "ja-JP", "gender": "male"},
    {"id": "pf_dora", "name": "Dora", "language": "pt", "locale": "pt-BR", "gender": "female"},
    {"id": "pm_alex", "name": "Alex", "language": "pt", "locale": "pt-BR", "gender": "male"},
    {"id": "zf_xiaobei", "name": "Xiaobei", "language": "zh", "locale": "zh-CN", "gender": "female"},
    {"id": "zm_yunjian", "name": "Yunjian", "language": "zh", "locale": "zh-CN", "gender": "male"},
]

LANGUAGE_NAMES = {"en": "English", "es": "Spanish", "fr": "French", "hi": "Hindi", "it": "Italian", "ja": "Japanese", "pt": "Portuguese", "zh": "Chinese"}


class TTSUnavailable(Exception):
    """No engine can speak this text in this language right now."""


def _base(language: str) -> str:
    return (language or "en").split("-")[0].lower()


@dataclass
class SpeechResult:
    audio: bytes
    content_type: str
    cached: bool


class KokoroEngine:
    """OpenAI-compatible speech endpoint (POST {base}/v1/audio/speech) of a self-hosted Kokoro server."""

    name = "kokoro"

    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        self.base_url = (base_url if base_url is not None else os.getenv("TTS_KOKORO_URL", "")).rstrip("/")
        self.timeout = timeout
        self._healthy_until = 0.0
        self._failures = 0
        self._cooldown_until = 0.0
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def voices(self, language: str | None = None) -> list[dict[str, str]]:
        if not self.configured:
            return []
        base = _base(language) if language else None
        return [voice for voice in KOKORO_VOICES if base is None or voice["language"] == base]

    def available(self) -> bool:
        return self.configured and time.time() >= self._cooldown_until

    def health(self) -> dict[str, object]:
        return {"configured": self.configured, "healthy": self.available(), "failures": self._failures, "cooldown_seconds": max(0, round(self._cooldown_until - time.time(), 1))}

    def synthesize(self, text: str, voice: str, speed: float = 1.0) -> tuple[bytes, str]:
        if not self.available():
            raise TTSUnavailable("engine_cooling_down")
        try:
            response = httpx.post(
                f"{self.base_url}/v1/audio/speech",
                json={"model": "kokoro", "input": text, "voice": voice, "response_format": "mp3", "speed": speed},
                timeout=self.timeout,
            )
            response.raise_for_status()
            if not response.content:
                raise TTSUnavailable("empty_audio")
        except (httpx.HTTPError, TTSUnavailable) as error:
            with self._lock:
                self._failures += 1
                self._cooldown_until = time.time() + min(300, 15 * (2 ** min(4, self._failures - 1)))  # circuit breaker
            raise TTSUnavailable("engine_error") from error
        with self._lock:
            self._failures = 0
        return response.content, response.headers.get("content-type", "audio/mpeg").split(";")[0]


class TTSRouter:
    def __init__(self, engines: list[KokoroEngine] | None = None, cache_dir: str | os.PathLike[str] | None = None) -> None:
        self.engines = engines if engines is not None else [KokoroEngine()]
        self.cache_dir = Path(cache_dir or os.getenv("TTS_CACHE_DIR") or (API_ROOT / "storage" / "tts-cache"))
        self.metrics = {"requests": 0, "cache_hits": 0, "failures": 0, "characters": 0}

    # ------------------------------------------------------------------ registry
    def voices(self, language: str) -> dict[str, object]:
        base = _base(language)
        neural: list[dict[str, object]] = []
        for engine in self.engines:
            for index, voice in enumerate(engine.voices(base)):
                neural.append({
                    "id": f"neural:{voice['id']}", "name": f"{voice['name']} — {LANGUAGE_NAMES.get(voice['language'], voice['language'])} ({voice['locale'].split('-')[1]})",
                    "language": voice["language"], "locale": voice["locale"], "gender": voice["gender"], "tier": "neural", "default": index == 0,
                })
        return {
            "language": language,
            "neural_available": bool(neural) and any(engine.available() for engine in self.engines),
            "voices": neural,
            # The browser voice is chosen on the device (exact locale > same language > none); described here so
            # the player can offer it in every language.
            "browser": {"id": "browser", "tier": "browser"},
        }

    def registry(self) -> list[dict[str, object]]:
        languages = sorted({voice["language"] for engine in self.engines for voice in engine.voices()})
        return [{"language": language, "voices": len(self.voices(language)["voices"])} for language in languages]

    def health(self) -> dict[str, object]:
        return {"engines": {engine.name: engine.health() for engine in self.engines}, "metrics": dict(self.metrics), "cache_dir_exists": self.cache_dir.exists()}

    # ------------------------------------------------------------------ speech
    def _engine_for(self, voice_id: str, language: str) -> tuple[KokoroEngine, dict[str, str]]:
        if not voice_id.startswith("neural:"):
            raise TTSUnavailable("browser_voice")
        raw = voice_id.split(":", 1)[1]
        for engine in self.engines:
            for voice in engine.voices():
                if voice["id"] == raw:
                    if voice["language"] != _base(language):
                        raise TTSUnavailable("wrong_language_voice")  # never read text with a wrong-language voice
                    return engine, voice
        raise TTSUnavailable("unknown_voice")

    def cache_key(self, voice_id: str, language: str, text: str) -> str:
        return hashlib.sha256(f"v1\x00{voice_id}\x00{_base(language)}\x00{text}".encode()).hexdigest()

    def synthesize(self, text: str, *, voice_id: str, language: str) -> SpeechResult:
        text = " ".join(text.split())[:1200]
        if not text:
            raise TTSUnavailable("empty_text")
        self.metrics["requests"] += 1
        engine, voice = self._engine_for(voice_id, language)
        key = self.cache_key(voice_id, language, text)
        path = self.cache_dir / key[:2] / f"{key}.mp3"
        if path.exists():
            self.metrics["cache_hits"] += 1
            return SpeechResult(path.read_bytes(), "audio/mpeg", True)
        try:
            audio, content_type = engine.synthesize(text, voice["id"])
        except TTSUnavailable:
            self.metrics["failures"] += 1
            raise
        self.metrics["characters"] += len(text)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(audio)
        tmp.replace(path)
        return SpeechResult(audio, content_type, False)


_router: TTSRouter | None = None


def get_tts_router() -> TTSRouter:
    global _router
    if _router is None:
        _router = TTSRouter()
    return _router


def set_tts_router(router: TTSRouter | None) -> None:
    """Tests replace the router with fake engines."""
    global _router
    _router = router
