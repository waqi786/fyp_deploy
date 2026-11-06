"""Search interface text for every supported language, filled on demand and cached on disk.

The web app ships pre-translated catalogs (apps/web/src/i18n/search-copy/<locale>.json). When a catalog is
missing labels (new features, stale files), the browser asks this service for the whole catalog of its
language. Missing labels are translated once with the public-text translation chain (`user_content=False`:
these are product labels, never user data), checked, cached on disk and served to every later visitor.

Guarantees:
  * placeholders such as {count} survive (masked as numbers and verified); a broken label is left out so the
    browser keeps a correct one instead of showing garbage;
  * product names (Resora, DOI, BibTeX, APA, CSV) are never translated;
  * a label is re-translated when its English text changes (per-label hashes);
  * only the English labels in ui_copy_en.json can be translated, so this is not a free translation API.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

SOURCE_FILE = Path(__file__).with_name("ui_copy_en.json")
LOCALES = {
    "ur", "ar", "fa", "hi", "bn", "pa-Arab", "tr", "id", "ms", "zh-Hans", "zh-Hant", "ja", "ko", "vi", "th",
    "es", "pt-BR", "pt-PT", "fr", "de", "it", "nl", "pl", "ru", "uk", "sv", "el", "ro", "cs", "hu", "he",
    "sw", "ta", "ps", "sd",
}
DO_NOT_TRANSLATE = {"exampleDoi", "yearRange"}
PROTECTED_TERMS = ["Resora", "BibTeX", "DOI", "APA", "CSV"]
PLACEHOLDER = re.compile(r"\{(\w+)\}")
MASK_BASE = 9301
BATCH_SIZE = 40
NATIVE_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹०१२३४५६७८९০১২৩৪৫৬৭৮৯", "0123456789" * 4)

Translator = Callable[[list[str], str], list[str]]


class UnsupportedLanguage(ValueError):
    pass


UI_SYSTEM_PROMPT = (
    "You are a senior software localizer. Translate short user-interface labels of a research search app "
    "from English into the target language. Use the natural wording native apps use for buttons, menus and "
    "messages (for example 'Home' is the start page, 'Saved' means bookmarked items, 'Gaps' means research gaps). "
    "Keep every number exactly as written: numbers stand for protected names and placeholders. "
    "Keep the meaning, tone and punctuation style. Do not add explanations. "
    "Return only a JSON object with the same keys and the translated strings as values."
)


def _language_name(target: str) -> str:
    try:
        from app.services.language.config import language_profile

        profile = language_profile(target)
        return f"{profile.english_name} ({profile.native_name})"
    except Exception:  # noqa: BLE001
        return target


def llm_translate_labels(values: list[str], target: str) -> list[str]:
    """Translate public UI labels with the AI router (`user_content=False`: product text, no user data)."""
    from app.services.ai_router import get_default_router

    router = get_default_router()
    candidates = [item.strip() for item in os.getenv("UI_COPY_TRANSLATION_TASK", "").split(",") if item.strip()]
    candidates += ["short_translation", "translation", "chat", "summary"]
    known = getattr(router, "routes", None)
    tasks = [task for task in dict.fromkeys(candidates) if not isinstance(known, dict) or task in known]
    if not tasks:
        raise RuntimeError("No AI task is configured for interface translation")
    payload = {str(index): value for index, value in enumerate(values)}
    prompt = json.dumps({"target_language": _language_name(target), "labels": payload}, ensure_ascii=False)

    def parse(text: str) -> dict[str, str] | None:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").split("\n", 1)[-1]
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict) or set(map(str, data)) != set(payload):
            return None
        return {str(key): str(value) for key, value in data.items()}

    last_error: Exception | None = None
    for task in tasks[:2]:
        try:
            response = router.complete(
                task,
                prompt,
                system=UI_SYSTEM_PROMPT,
                user_content=False,
                model_family="translation:ui",
                max_tokens=min(4096, 400 + sum(len(value) for value in values) * 3),
                validator=lambda text: parse(text) is not None,
                language=target,
            )
            parsed = parse(response.text)
            if parsed is not None:
                return [parsed[str(index)] for index in range(len(values))]
        except Exception as error:  # noqa: BLE001 - try the next task, then the translation chain
            last_error = error
    raise RuntimeError("AI interface translation is unavailable") from last_error


def _default_translator(values: list[str], target: str) -> list[str]:
    """Prefer the AI router (fluent UI wording); fall back to the translation chain."""
    try:
        return llm_translate_labels(values, target)
    except Exception:  # noqa: BLE001
        from app.services.search.translation import translate_batch

        return translate_batch(values, target, source_language="en", user_content=False)


def _text_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _placeholders(value: str) -> list[str]:
    return sorted(PLACEHOLDER.findall(value))


def _mask(value: str) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}
    counter = MASK_BASE

    def take(original: str) -> str:
        nonlocal counter
        token = str(counter)
        counter += 1
        mapping[token] = original
        return token

    masked = PLACEHOLDER.sub(lambda match: take(match.group(0)), value)
    for term in PROTECTED_TERMS:
        if term in masked:
            masked = masked.replace(term, take(term))
    return masked, mapping


def _unmask(value: str, mapping: dict[str, str]) -> str | None:
    restored = value.translate(NATIVE_DIGITS) if mapping else value
    for token, original in mapping.items():
        spaced = re.compile(r"\s?".join(token))
        if not spaced.search(restored):
            return None
        restored = spaced.sub(lambda _match: original, restored, count=1)
    return " ".join(restored.split())


def _usable(english: str, translated: str | None) -> bool:
    if not translated or not translated.strip():
        return False
    if _placeholders(translated) != _placeholders(english):
        return False
    if "→" in translated and "→" not in english:  # a known artefact of some engines
        return False
    return len(translated) <= max(40, len(english) * 4)


class SearchUiCopyService:
    def __init__(self, cache_dir: str | os.PathLike[str] | None = None, translator: Translator | None = None):
        self.cache_dir = Path(cache_dir or os.getenv("UI_COPY_CACHE_DIR", "storage/ui-copy"))
        self.translator = translator or _default_translator
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self._source: dict[str, str] | None = None

    # ------------------------------------------------------------------ data
    def source(self) -> dict[str, str]:
        if self._source is None:
            data = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))
            self._source = {str(key): str(value) for key, value in data.items()}
        return self._source

    def _cache_file(self, language: str) -> Path:
        return self.cache_dir / f"{language}.json"

    def _load(self, language: str) -> dict:
        try:
            data = json.loads(self._cache_file(language).read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("messages"), dict) and isinstance(data.get("hashes"), dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return {"messages": {}, "hashes": {}}

    def _save(self, language: str, data: dict) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_file(language)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(path)

    def _lock(self, language: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(language, threading.Lock())

    # ------------------------------------------------------------------ public
    def catalog(self, language: str) -> dict[str, object]:
        if language not in LOCALES:
            raise UnsupportedLanguage(language)
        source = self.source()
        with self._lock(language):
            data = self._load(language)
            messages: dict[str, str] = {key: value for key, value in data["messages"].items() if key in source}
            hashes: dict[str, str] = {key: value for key, value in data["hashes"].items() if key in source}
            pending = [
                (key, english)
                for key, english in source.items()
                if hashes.get(key) != _text_hash(english) or key not in messages
            ]
            failed = 0
            for key, english in [item for item in pending if item[0] in DO_NOT_TRANSLATE]:
                messages[key] = english
                hashes[key] = _text_hash(english)
            pending = [item for item in pending if item[0] not in DO_NOT_TRANSLATE]
            for offset in range(0, len(pending), BATCH_SIZE):
                chunk = pending[offset : offset + BATCH_SIZE]
                masked = [_mask(english) for _, english in chunk]
                try:
                    outputs = self.translator([text for text, _ in masked], language)
                except Exception:  # noqa: BLE001 - any engine failure: serve what we have
                    logger.warning("Search UI copy translation failed for %s", language, exc_info=True)
                    failed += len(pending) - offset
                    break
                if len(outputs) != len(chunk):
                    failed += len(chunk)
                    continue
                for (key, english), (_, mapping), output in zip(chunk, masked, outputs):
                    restored = _unmask(output, mapping) if output else None
                    if _usable(english, restored):
                        messages[key] = restored  # type: ignore[assignment]
                        hashes[key] = _text_hash(english)
                    else:
                        failed += 1
            if pending:
                self._save(language, {"messages": messages, "hashes": hashes})
        return {"language": language, "messages": messages, "complete": failed == 0 and len(messages) == len(source)}


_service: SearchUiCopyService | None = None


def get_ui_copy_service() -> SearchUiCopyService:
    global _service
    if _service is None:
        _service = SearchUiCopyService()
    return _service