from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import time
import uuid
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

import httpx

from app.core.config import settings
from app.services.language.config import (
    canonical_language_code,
    detect_language,
    language_profile,
)

logger = logging.getLogger(__name__)


class TranslationUnavailable(RuntimeError):
    """No configured provider could translate the text; callers should show originals."""


class TranslationIntegrityError(TranslationUnavailable):
    pass


@dataclass(frozen=True)
class ProviderLimits:
    requests_per_second: float
    characters_per_minute: int
    max_batch_size: int
    max_chars_per_batch: int


class TranslationProvider(Protocol):
    name: str
    limits: ProviderLimits

    def supports(self, source: str, target: str) -> bool: ...
    def translate_batch(self, segments: Sequence[str], source: str, target: str, glossary: dict[str, str] | None = None) -> list[str]: ...


_PROTECTED = re.compile(
    r"https?://[^\s<>]+|10\.\d{4,9}/[-._;()/:a-zA-Z0-9]*[a-zA-Z0-9]|`[^`]*`|"
    r"\$[^$]+\$|\\\([^\n]*?\\\)|\[[0-9]+(?:[,;\- ]+[0-9]+)*\]|"
    r"(?<![A-Za-z])\d+(?:[.,]\d+)*(?:\s?(?:%|ms|s|kg|mg|mm|cm|km|\u00b0?C|\u00b0?F))?(?![A-Za-z])|"
    r"\b[A-Za-z][A-Za-z0-9_]*\s*\^\s*\d+",
    re.IGNORECASE,
)
_TOKEN = "RESORATOKENX{index}XEND"
_CACHE: OrderedDict[tuple[str, str, str, str], str] = OrderedDict()
_CACHE_LOCK = threading.RLock()
_CACHE_LIMIT = 4096
_CACHE_VERSION = "resora-glossary-v2"
_INFLIGHT: dict[tuple[str, str, str, str], threading.Event] = {}
_PROVIDER_LOCK = threading.RLock()
_PROVIDER_LAST_CALL: dict[str, float] = {}
_PROVIDER_COOLDOWN: dict[str, float] = {}
_PROVIDER_FAILURES: dict[str, int] = {}
_METRICS: dict[str, dict[str, float]] = {}
_CHAR_USAGE: dict[str, deque[tuple[float, int]]] = {}
_PROVIDER_HEALTH: dict[str, dict[str, object]] = {}
_REDIS_CLIENT = None
_REDIS_CLIENT_LOCK = threading.Lock()
_REDIS_DOWN_UNTIL = 0.0
_REDIS_LAST_PING = 0.0
_BUDGET_USAGE: dict[tuple[str, str], int] = {}
_USER_BUDGET_USAGE: dict[tuple[str, str], int] = {}
_RETRY_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="translation-retry")
_RETRY_BOOKKEEPING_LIMIT = 4096
_RETRY_LOCK = threading.Lock()
_RETRY_PENDING: set[str] = set()
_RETRY_LAST_SCHEDULED: dict[str, float] = {}
_RETRY_STATUS_LOCAL: dict[str, dict[str, object]] = {}
_RETRY_DEDUPE_LOCAL: dict[str, str] = {}
_RETRY_WORKER_RUNNING = False
_BUCKET_LUA = """
local now = tonumber(ARGV[1])
local req_rate = tonumber(ARGV[2])
local req_capacity = tonumber(ARGV[3])
local chars_rate = tonumber(ARGV[4])
local chars_capacity = tonumber(ARGV[5])
local chars_cost = tonumber(ARGV[6])
local req_tokens = tonumber(redis.call('HGET', KEYS[1], 'tokens')) or req_capacity
local req_updated = tonumber(redis.call('HGET', KEYS[1], 'updated')) or now
local char_tokens = tonumber(redis.call('HGET', KEYS[2], 'tokens')) or chars_capacity
local char_updated = tonumber(redis.call('HGET', KEYS[2], 'updated')) or now
req_tokens = math.min(req_capacity, req_tokens + math.max(0, now - req_updated) * req_rate)
char_tokens = math.min(chars_capacity, char_tokens + math.max(0, now - char_updated) * chars_rate)
if req_tokens < 1 or char_tokens < chars_cost then return 0 end
redis.call('HSET', KEYS[1], 'tokens', req_tokens - 1, 'updated', now)
redis.call('EXPIRE', KEYS[1], 120)
redis.call('HSET', KEYS[2], 'tokens', char_tokens - chars_cost, 'updated', now)
redis.call('EXPIRE', KEYS[2], 120)
return 1
"""
_BUDGET_LUA = """
local chars = tonumber(ARGV[1])
local month_limit = tonumber(ARGV[2])
local day_limit = tonumber(ARGV[3])
local user_limit = tonumber(ARGV[4])
local month_used = tonumber(redis.call('GET', KEYS[1])) or 0
local day_used = tonumber(redis.call('GET', KEYS[2])) or 0
local user_used = tonumber(redis.call('GET', KEYS[3])) or 0
if month_limit > 0 and month_used + chars >= month_limit * 0.9 then return 0 end
if day_limit > 0 and day_used + chars >= day_limit * 0.9 then return 0 end
if user_limit > 0 and user_used + chars > user_limit then return 0 end
redis.call('INCRBY', KEYS[1], chars); redis.call('EXPIRE', KEYS[1], 2764800)
redis.call('INCRBY', KEYS[2], chars); redis.call('EXPIRE', KEYS[2], 172800)
if user_limit > 0 then redis.call('INCRBY', KEYS[3], chars); redis.call('EXPIRE', KEYS[3], 172800) end
return 1
"""


def _redis():
    global _REDIS_CLIENT, _REDIS_DOWN_UNTIL, _REDIS_LAST_PING
    if not settings.redis_url:
        return None
    if time.monotonic() < _REDIS_DOWN_UNTIL:
        return None
    if _REDIS_CLIENT is None:
        with _REDIS_CLIENT_LOCK:
            if _REDIS_CLIENT is None:
                try:
                    import redis
                    _REDIS_CLIENT = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=0.25, socket_timeout=0.25)
                except Exception:
                    _REDIS_DOWN_UNTIL = time.monotonic() + 5
                    return None
    now = time.monotonic()
    if _REDIS_CLIENT is not None and now - _REDIS_LAST_PING >= 5:
        try:
            _REDIS_CLIENT.ping()
            _REDIS_LAST_PING = now
        except Exception:
            _REDIS_LAST_PING = now
            _REDIS_DOWN_UNTIL = now + 5
            return None
    return _REDIS_CLIENT


def _redis_circuit_active(provider: str) -> bool:
    client = _redis()
    if client is None:
        return False
    try:
        return bool(client.exists(f"resora:translation:circuit:{provider}"))
    except Exception:
        return False


def _set_redis_circuit(provider: str, seconds: float) -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.set(f"resora:translation:circuit:{provider}", "open", ex=max(1, int(seconds)))
    except Exception:
        pass


def _clear_redis_circuit(provider: str) -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.delete(f"resora:translation:circuit:{provider}")
    except Exception:
        pass


def _redis_bucket_allow(provider: TranslationProvider, char_count: int) -> bool | None:
    client = _redis()
    if client is None:
        return None
    try:
        result = client.eval(
            _BUCKET_LUA, 2,
            f"resora:translation:bucket:{provider.name}:requests",
            f"resora:translation:bucket:{provider.name}:characters",
            time.time(), provider.limits.requests_per_second,
            max(1, provider.limits.requests_per_second),
            provider.limits.characters_per_minute / 60,
            provider.limits.characters_per_minute, max(1, char_count),
        )
        return bool(result)
    except Exception:
        return None


def _budget_config(env_name: str) -> dict[str, int]:
    try:
        parsed = json.loads(os.getenv(env_name, "{}"))
        return {str(key): max(0, int(value)) for key, value in parsed.items()}
    except (ValueError, TypeError, json.JSONDecodeError):
        logger.warning("Invalid translation budget configuration", extra={"setting": env_name})
        return {}


def _budget_periods() -> tuple[str, str]:
    now = time.gmtime()
    return time.strftime("%Y%m", now), time.strftime("%Y%m%d", now)


def _budget_used(provider: str, period: str) -> int:
    key = f"{provider}:{period}"
    client = _redis()
    if client is not None:
        try:
            return int(client.get(f"resora:translation:usage:{key}") or 0)
        except Exception:
            pass
    return _BUDGET_USAGE.get((provider, period), 0)


def _provider_within_budget(provider: str, chars: int) -> bool:
    monthly, daily = _budget_config("TRANSLATION_MONTHLY_CHARACTER_BUDGETS"), _budget_config("TRANSLATION_DAILY_CHARACTER_BUDGETS")
    month_key, day_key = _budget_periods()
    for config, period in ((monthly, month_key), (daily, day_key)):
        budget = config.get(provider)
        if budget and _budget_used(provider, period) + chars >= budget * 0.9:
            return False
    return True


def _reserve_translation_usage(provider: str, chars: int, user_id: str | None = None) -> bool:
    monthly = _budget_config("TRANSLATION_MONTHLY_CHARACTER_BUDGETS").get(provider, 0)
    daily = _budget_config("TRANSLATION_DAILY_CHARACTER_BUDGETS").get(provider, 0)
    user_daily = max(0, int(os.getenv("TRANSLATION_USER_DAILY_CHARACTER_LIMIT", "100000"))) if user_id else 0
    month_key, day_key = _budget_periods()
    user_key = f"{(user_id or 'anonymous').strip() or 'anonymous'}:{day_key}"
    client = _redis()
    if client is not None:
        try:
            result = client.eval(
                _BUDGET_LUA, 3,
                f"resora:translation:usage:{provider}:{month_key}",
                f"resora:translation:usage:{provider}:{day_key}",
                f"resora:translation:user-usage:{user_key}",
                max(0, chars), monthly, daily, user_daily,
            )
            return bool(result)
        except Exception:
            logger.warning("Redis translation quota reservation failed; using process-local quota", exc_info=True)
    with _PROVIDER_LOCK:
        for limit, key in ((monthly, (provider, month_key)), (daily, (provider, day_key))):
            if limit and _BUDGET_USAGE.get(key, 0) + chars >= limit * 0.9:
                return False
        local_user_key = (user_key, day_key)
        if user_daily and _USER_BUDGET_USAGE.get(local_user_key, 0) + chars > user_daily:
            return False
        key = (provider, month_key)
        _BUDGET_USAGE[key] = _BUDGET_USAGE.get(key, 0) + chars
        key = (provider, day_key)
        _BUDGET_USAGE[key] = _BUDGET_USAGE.get(key, 0) + chars
        if user_daily:
            _USER_BUDGET_USAGE[local_user_key] = _USER_BUDGET_USAGE.get(local_user_key, 0) + chars
        return True


def _record_budget_usage(provider: str, chars: int) -> None:
    month_key, day_key = _budget_periods()
    client = _redis()
    for period, expiry in ((month_key, 32 * 24 * 3600), (day_key, 2 * 24 * 3600)):
        key = f"{provider}:{period}"
        if client is not None:
            try:
                redis_key = f"resora:translation:usage:{key}"
                client.incrby(redis_key, chars)
                client.expire(redis_key, expiry)
                continue
            except Exception:
                pass
        _BUDGET_USAGE[(provider, period)] = _BUDGET_USAGE.get((provider, period), 0) + chars


def translation_budget_status() -> dict[str, dict[str, int | None]]:
    month_key, day_key = _budget_periods()
    monthly = _budget_config("TRANSLATION_MONTHLY_CHARACTER_BUDGETS")
    daily = _budget_config("TRANSLATION_DAILY_CHARACTER_BUDGETS")
    providers = set(monthly) | set(daily) | {name for name, _ in _BUDGET_USAGE}
    return {
        name: {
            "month_used": _budget_used(name, month_key),
            "month_limit": monthly.get(name),
            "day_used": _budget_used(name, day_key),
            "day_limit": daily.get(name),
        }
        for name in sorted(providers)
    }


def _protect(text: str) -> tuple[str, list[str]]:
    protected: list[str] = []

    def replace(match: re.Match[str]) -> str:
        token = _TOKEN.format(index=len(protected))
        protected.append(match.group(0))
        return token

    return _PROTECTED.sub(replace, text), protected


def _restore(text: str, protected: list[str]) -> str:
    restored = text
    for index, original in enumerate(protected):
        token = _TOKEN.format(index=index)
        match = re.search(re.escape(token), restored, re.IGNORECASE)
        if match is None:
            raise TranslationIntegrityError("A provider changed protected academic text.")
        restored = restored[:match.start()] + original + restored[match.end():]
    if re.search(r"RESORATOKENX\d+XEND", restored, re.IGNORECASE):
        raise TranslationIntegrityError("A provider returned an unknown protection token.")
    return restored


def _provider_code(code: str) -> str:
    mappings = {"zh-Hans": "zh-CN", "zh-Hant": "zh-TW", "pa-Arab": "pa", "pt-BR": "pt", "pt-PT": "pt-PT", "he": "he"}
    return mappings.get(code, code)


class OfficialGoogleCloudProvider:
    name = "google_cloud"
    limits = ProviderLimits(5, 900_000, 50, 25_000)

    def supports(self, source: str, target: str) -> bool:
        return bool(os.getenv("GOOGLE_TRANSLATE_PROJECT_ID")) and target != "pa-Arab"

    def translate_batch(self, segments: Sequence[str], source: str, target: str, glossary: dict[str, str] | None = None) -> list[str]:
        try:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-translation"])
        except Exception as exc:
            raise TranslationUnavailable("Google Cloud credentials are unavailable.") from exc
        project = os.getenv("GOOGLE_TRANSLATE_PROJECT_ID", "")
        location = os.getenv("GOOGLE_TRANSLATE_LOCATION", "global")
        url = f"https://translation.googleapis.com/v3/projects/{project}/locations/{location}:translateText"
        payload: dict[str, object] = {
            "contents": list(segments), "mimeType": "text/plain", "targetLanguageCode": _provider_code(target),
            "model": os.getenv("GOOGLE_TRANSLATE_MODEL", "general/nmt"),
        }
        if source != "auto":
            payload["sourceLanguageCode"] = _provider_code(source)
        glossary_name = os.getenv("GOOGLE_TRANSLATE_GLOSSARY_NAME")
        if glossary_name:
            payload["glossaryConfig"] = {"glossary": glossary_name, "ignoreCase": True}
        try:
            response = AuthorizedSession(credentials).post(url, json=payload, timeout=8)
            response.raise_for_status()
            values = response.json().get("translations", [])
            results = [item.get("translatedText", "") for item in values]
            if len(results) != len(segments) or any(not item for item in results):
                raise TranslationUnavailable("Google Cloud returned an incomplete batch.")
            return results
        except Exception as exc:
            raise _provider_error("google_cloud", exc) from exc


class AzureTranslatorProvider:
    name = "azure"
    limits = ProviderLimits(5, 1_500_000, 25, 5_000)

    def supports(self, source: str, target: str) -> bool:
        return bool(os.getenv("AZURE_TRANSLATOR_KEY"))

    def translate_batch(self, segments: Sequence[str], source: str, target: str, glossary: dict[str, str] | None = None) -> list[str]:
        key = os.getenv("AZURE_TRANSLATOR_KEY", "")
        region = os.getenv("AZURE_TRANSLATOR_REGION", "")
        endpoint = os.getenv("AZURE_TRANSLATOR_ENDPOINT", "https://api.cognitive.microsofttranslator.com").rstrip("/")
        params: list[tuple[str, str]] = [("api-version", "3.0"), ("to", _provider_code(target))]
        if source != "auto":
            params.append(("from", _provider_code(source)))
        if target == "pa-Arab":
            params.append(("toScript", "Arab"))
        if source == "pa-Arab":
            params.append(("fromScript", "Arab"))
        headers = {"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/json"}
        if region:
            headers["Ocp-Apim-Subscription-Region"] = region
        try:
            response = httpx.post(f"{endpoint}/translate", params=params, headers=headers, json=[{"Text": item} for item in segments], timeout=8)
            response.raise_for_status()
            results = [item["translations"][0]["text"] for item in response.json()]
            if len(results) != len(segments) or any(not item for item in results):
                raise TranslationUnavailable("Azure returned an incomplete batch.")
            return results
        except Exception as exc:
            raise _provider_error("azure", exc) from exc


class DeepLProvider:
    name = "deepl"
    limits = ProviderLimits(3, 500_000, 50, 25_000)
    supported = {"en", "ur", "ar", "bg", "cs", "da", "de", "el", "es", "et", "fi", "fr", "hu", "id", "it", "ja", "ko", "lt", "lv", "nb", "nl", "pl", "pt-BR", "pt-PT", "ro", "ru", "sk", "sl", "sv", "tr", "uk", "zh-Hans"}

    def supports(self, source: str, target: str) -> bool:
        return bool(os.getenv("DEEPL_API_KEY")) and target in self.supported and (source == "auto" or source in self.supported)

    def translate_batch(self, segments: Sequence[str], source: str, target: str, glossary: dict[str, str] | None = None) -> list[str]:
        key = os.getenv("DEEPL_API_KEY", "")
        target_code = {"zh-Hans": "ZH", "pt-BR": "PT-BR", "pt-PT": "PT-PT", "en": "EN-US"}.get(target, target.upper())
        base = "https://api-free.deepl.com" if key.endswith(":fx") else "https://api.deepl.com"
        payload: list[tuple[str, str]] = [("text", value) for value in segments]
        payload.append(("target_lang", target_code))
        if source != "auto":
            payload.append(("source_lang", {"zh-Hans": "ZH", "en": "EN"}.get(source, source.upper())))
        try:
            response = httpx.post(f"{base}/v2/translate", data=payload, headers={"Authorization": f"DeepL-Auth-Key {key}"}, timeout=8)
            response.raise_for_status()
            results = [item["text"] for item in response.json().get("translations", [])]
            if len(results) != len(segments) or any(not item for item in results):
                raise TranslationUnavailable("DeepL returned an incomplete batch.")
            return results
        except Exception as exc:
            raise _provider_error("deepl", exc) from exc


class MADLADSelfHostedProvider:
    name = "madlad"
    limits = ProviderLimits(8, 10_000_000, 24, 24_000)

    def supports(self, source: str, target: str) -> bool:
        configured = bool(os.getenv("SELFHOSTED_TRANSLATOR_URL"))
        health = _PROVIDER_HEALTH.get(self.name)
        return configured and not (health and health.get("status") == "unhealthy")

    def translate_batch(self, segments: Sequence[str], source: str, target: str, glossary: dict[str, str] | None = None) -> list[str]:
        endpoint = os.getenv("SELFHOSTED_TRANSLATOR_URL", "http://translator:8090").rstrip("/")
        try:
            response = httpx.post(f"{endpoint}/translate", json={"segments": list(segments), "source_language": source, "target_language": target}, timeout=float(getattr(settings, "translation_timeout_seconds", 20)))
            response.raise_for_status()
            results = response.json().get("translations", [])
            if len(results) != len(segments) or any(not item for item in results):
                raise TranslationUnavailable("MADLAD returned an incomplete batch.")
            return results
        except Exception as exc:
            raise _provider_error("madlad", exc) from exc


class ArgosLocalProvider:
    """Local, key-free Argos -> M2M-100 -> OPUS-MT fallback service."""

    name = "translator_local"
    limits = ProviderLimits(4, 120_000, 20, 8_000)

    def supports(self, source: str, target: str) -> bool:
        endpoint = os.getenv("LOCAL_TRANSLATOR_URL", "").strip()
        health = _PROVIDER_HEALTH.get(self.name)
        engines = health.get("engines", {}) if health else {}
        available = any(isinstance(item, dict) and item.get("status") == "available" for item in engines.values())
        if health is None:
            configured = {item.strip() for item in os.getenv("LOCAL_TRANSLATION_LANGUAGES", "").split(",") if item.strip()}
            return bool(endpoint) and source in configured and target in configured
        return bool(endpoint) and available and not (health and health.get("status") == "unhealthy")

    def translate_batch(self, segments: Sequence[str], source: str, target: str, glossary: dict[str, str] | None = None) -> list[str]:
        endpoint = os.getenv("LOCAL_TRANSLATOR_URL", "http://translator-local:8091").rstrip("/")
        try:
            response = httpx.post(
                f"{endpoint}/translate",
                json={"segments": list(segments), "source_language": source, "target_language": target},
                timeout=float(getattr(settings, "translation_timeout_seconds", 8)),
            )
            response.raise_for_status()
            results = response.json().get("translations", [])
            if not isinstance(results, list) or len(results) != len(segments) or any(not isinstance(item, str) or not item.strip() for item in results):
                raise TranslationUnavailable("Local translator returned an incomplete batch.")
            for engine in response.json().get("engines_used", []):
                metric = _METRICS.setdefault(f"local_{engine}", {})
                metric["successes"] = metric.get("successes", 0) + 1
            return results
        except Exception as exc:
            raise _provider_error("translator_local", exc) from exc


def _local_language_code(code: str) -> str:
    return {"zh-Hans": "zh", "zh-Hant": "zt", "pt-BR": "pb", "pt-PT": "pt", "pa-Arab": "pa"}.get(code, code.split("-")[0])


class GroqTranslationProvider:
    name = "groq"
    limits = ProviderLimits(1, 100_000, 8, 8_000)

    def supports(self, source: str, target: str) -> bool:
        return bool(getattr(settings, "groq_api_key", None))

    def translate_batch(self, segments: Sequence[str], source: str, target: str, glossary: dict[str, str] | None = None) -> list[str]:
        profile = language_profile(target)
        glossary_text = "\n".join(f"{key} => {value}" for key, value in (glossary or {}).items())
        prompt = json.dumps({"segments": list(segments), "source_language": source,
                             "target_language": f"{profile.english_name} ({profile.native_name})",
                             "glossary": glossary_text}, ensure_ascii=False)
        try:
            from app.services.ai_router import RouterUnavailable, get_default_router

            response = get_default_router().complete(
                "short_translation", prompt,
                system="Translate every segment faithfully as academic prose. Preserve all protected tokens exactly. Return only a JSON array of strings with the same length and order.",
                user_content=True,
                model_family="translation",
                max_tokens=min(4096, max(512, sum(len(item) for item in segments) // 2)),
                validator=lambda output: _valid_translation_batch(output, segments, target),
                language=target,
            )
            decoded = json.loads(response.text)
            results = decoded if isinstance(decoded, list) else decoded.get("translations")
            if not isinstance(results, list) or len(results) != len(segments) or any(not isinstance(item, str) or not item for item in results):
                raise TranslationUnavailable("Hosted translation returned an invalid batch.")
            return results
        except RouterUnavailable as exc:
            raise TranslationUnavailable("No approved hosted translation provider is currently available.") from exc
        except Exception as exc:
            raise _provider_error("ai_router_translation", exc) from exc


def _valid_translation_array(output: str, expected_count: int) -> bool:
    try:
        decoded = json.loads(output)
        values = decoded if isinstance(decoded, list) else decoded.get("translations")
        return isinstance(values, list) and len(values) == expected_count and all(isinstance(value, str) and value.strip() for value in values)
    except (ValueError, TypeError, AttributeError):
        return False


def _valid_translation_batch(output: str, source_segments: Sequence[str], target: str) -> bool:
    if not _valid_translation_array(output, len(source_segments)):
        return False
    try:
        from app.services.ai_router.validators import translation_output_is_valid

        decoded = json.loads(output)
        values = decoded if isinstance(decoded, list) else decoded.get("translations")
        return all(translation_output_is_valid(source, translated, target)
                   for source, translated in zip(source_segments, values))
    except (ValueError, TypeError, AttributeError):
        return False


def _provider_error(provider: str, exc: Exception) -> TranslationUnavailable:
    retry_after = None
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code == 429:
        raw = getattr(response, "headers", {}).get("Retry-After", "30")
        try:
            retry_after = max(1.0, min(float(raw), 3600.0))
        except (TypeError, ValueError):
            retry_after = 30.0
    with _PROVIDER_LOCK:
        failures = _PROVIDER_FAILURES.get(provider, 0) + 1
        _PROVIDER_FAILURES[provider] = failures
        retry_after = retry_after or min(300.0, 2.0 ** min(failures, 8))
        _PROVIDER_COOLDOWN[provider] = time.monotonic() + retry_after
    _set_redis_circuit(provider, retry_after)
    metrics = _METRICS.setdefault(provider, {})
    metrics["errors"] = metrics.get("errors", 0) + 1
    if status_code == 429:
        metrics["rate_limits"] = metrics.get("rate_limits", 0) + 1
    return TranslationUnavailable(f"{provider} unavailable")


_PROVIDERS: dict[str, TranslationProvider] = {
    "google_cloud": OfficialGoogleCloudProvider(), "azure": AzureTranslatorProvider(),
    "deepl": DeepLProvider(), "madlad": MADLADSelfHostedProvider(), "groq": GroqTranslationProvider(),
    "translator_local": ArgosLocalProvider(),
}


def _provider_order(target: str) -> list[str]:
    raw_overrides = os.getenv("TRANSLATION_LANGUAGE_ROUTES", "")
    if raw_overrides:
        try:
            routes = json.loads(raw_overrides)
            for key, value in routes.items():
                if canonical_language_code(key) == target and isinstance(value, list):
                    return [str(item) for item in value]
        except (ValueError, TypeError, json.JSONDecodeError):
            logger.warning("Invalid TRANSLATION_LANGUAGE_ROUTES; using default route")
    configured = os.getenv("TRANSLATION_PROVIDER_ORDER", "translator_local,azure,google_cloud,deepl,groq")
    return [item.strip().lower() for item in configured.split(",") if item.strip()]


def _rate_limit(provider: TranslationProvider, char_count: int, user_id: str | None = None) -> None:
    """Enforce circuit breakers, spacing between calls and character budgets for one provider call.

    The spacing sleep happens outside the shared lock so one slow provider never blocks the others.
    """
    if _redis_circuit_active(provider.name):
        raise TranslationUnavailable(f"{provider.name} circuit is open")
    with _PROVIDER_LOCK:
        now = time.monotonic()
        if _PROVIDER_COOLDOWN.get(provider.name, 0) > now:
            raise TranslationUnavailable(f"{provider.name} cooling down")
        interval = 1 / max(provider.limits.requests_per_second, 0.01)
        wait = interval - (now - _PROVIDER_LAST_CALL.get(provider.name, 0))
        # Reserve the slot now so concurrent callers queue behind us instead of all sleeping the same amount.
        _PROVIDER_LAST_CALL[provider.name] = now + max(0.0, wait)
    if wait > 0:
        time.sleep(min(wait, 2.0))
    distributed = _redis_bucket_allow(provider, char_count)
    if distributed is False:
        raise TranslationUnavailable(f"{provider.name} shared rate limit reached")
    with _PROVIDER_LOCK:
        now = time.monotonic()
        usage = _CHAR_USAGE.setdefault(provider.name, deque())
        while usage and now - usage[0][0] >= 60:
            usage.popleft()
        if sum(amount for _, amount in usage) + char_count > provider.limits.characters_per_minute:
            raise TranslationUnavailable(f"{provider.name} local character budget reached")
        if not _reserve_translation_usage(provider.name, char_count, user_id):
            raise TranslationUnavailable(f"{provider.name} or user character budget reached")
        usage.append((now, char_count))
        metrics = _METRICS.setdefault(provider.name, {})
        metrics["calls"] = metrics.get("calls", 0) + 1
        metrics["chars"] = metrics.get("chars", 0) + char_count


def _provider_success(name: str, started: float) -> None:
    """Close the provider's breaker after a good call and record latency."""
    with _PROVIDER_LOCK:
        _PROVIDER_FAILURES[name] = 0
        _PROVIDER_COOLDOWN.pop(name, None)
        metrics = _METRICS.setdefault(name, {})
        metrics["successes"] = metrics.get("successes", 0) + 1
        metrics["latency_ms"] = metrics.get("latency_ms", 0) + (time.perf_counter() - started) * 1000


def translation_metrics() -> dict[str, dict[str, float]]:
    now = time.monotonic()
    with _PROVIDER_LOCK:
        names = set(_METRICS) | set(_PROVIDER_COOLDOWN)
        return {
            name: {**_METRICS.get(name, {}), "cooldown_seconds": max(0.0, _PROVIDER_COOLDOWN.get(name, 0.0) - now)}
            for name in names
        }


def translation_provider_health() -> dict[str, dict[str, object]]:
    with _PROVIDER_LOCK:
        return {name: dict(value) for name, value in _PROVIDER_HEALTH.items()}


def _provider_missing_reason(name: str) -> str | None:
    configured = {
        "azure": bool(os.getenv("AZURE_TRANSLATOR_KEY")),
        "google_cloud": bool(os.getenv("GOOGLE_TRANSLATE_PROJECT_ID")),
        "deepl": bool(os.getenv("DEEPL_API_KEY")),
        "groq": bool(getattr(settings, "groq_api_key", None)),
        "madlad": bool(os.getenv("SELFHOSTED_TRANSLATOR_URL")),
        "translator_local": bool(os.getenv("LOCAL_TRANSLATOR_URL")),
    }.get(name, False)
    return None if configured else "missing_key_or_endpoint"


def check_translation_provider_health() -> dict[str, dict[str, object]]:
    """Probe configured providers with a short, non-sensitive translation."""
    for name, provider in _PROVIDERS.items():
        missing = _provider_missing_reason(name)
        if missing:
            state: dict[str, object] = {"status": "unhealthy", "reason": missing, "checked_at": time.time()}
        else:
            try:
                # Let a later successful probe recover a provider previously
                # disabled by an outage; `supports` consults health state.
                with _PROVIDER_LOCK:
                    _PROVIDER_HEALTH.pop(name, None)
                state = {"status": "healthy", "reason": None, "checked_at": time.time()}
                if name == "translator_local":
                    endpoint = os.getenv("LOCAL_TRANSLATOR_URL", "http://translator-local:8091").rstrip("/")
                    service_health = httpx.get(f"{endpoint}/health", timeout=3)
                    service_health.raise_for_status()
                    language_response = httpx.get(f"{endpoint}/languages", timeout=3)
                    language_response.raise_for_status()
                    if service_health.json().get("status") != "ready":
                        raise TranslationUnavailable("local model inventory is not ready")
                    state.update(language_response.json())
                else:
                    if not provider.supports("en", "es"):
                        raise TranslationUnavailable("provider does not support probe languages")
                    _rate_limit(provider, len("Resora health check"))
                    provider.translate_batch(["Resora health check"], "en", "es")
            except Exception as exc:
                response = getattr(exc, "response", None)
                status = getattr(response, "status_code", None)
                reason = "rate_limited" if status == 429 else "unauthorized" if status in {401, 403} else "down"
                state = {"status": "unhealthy", "reason": reason, "checked_at": time.time()}
        with _PROVIDER_LOCK:
            _PROVIDER_HEALTH[name] = state
    return translation_provider_health()


def _cache_path() -> Path:
    return Path(os.getenv("TRANSLATION_CACHE_PATH", "storage/translation_cache.sqlite3"))


_SQLITE_READY: set[str] = set()
_SQLITE_LOCK = threading.Lock()


def _sqlite_connect(timeout: float) -> sqlite3.Connection:
    path = _cache_path()
    key = str(path)
    if key not in _SQLITE_READY:
        with _SQLITE_LOCK:
            if key not in _SQLITE_READY:
                path.parent.mkdir(parents=True, exist_ok=True)
                with sqlite3.connect(path, timeout=timeout) as connection:
                    connection.execute("PRAGMA journal_mode=WAL")
                    connection.execute("CREATE TABLE IF NOT EXISTS translation_cache (cache_key TEXT PRIMARY KEY, translated_text TEXT NOT NULL, created_at REAL NOT NULL)")
                _SQLITE_READY.add(key)
    return sqlite3.connect(path, timeout=timeout)


def _persistent_cache_get(key: str) -> str | None:
    client = _redis()
    if client is not None:
        try:
            value = client.get(f"resora:translation:cache:{key}")
            if value is not None:
                return str(value)
        except Exception:
            pass
    try:
        with _sqlite_connect(timeout=1) as connection:
            row = connection.execute("SELECT translated_text FROM translation_cache WHERE cache_key = ?", (key,)).fetchone()
            return row[0] if row else None
    except sqlite3.Error:
        return None


def _persistent_cache_set(key: str, value: str) -> None:
    client = _redis()
    if client is not None:
        try:
            client.set(f"resora:translation:cache:{key}", value, ex=30 * 24 * 3600)
        except Exception:
            pass
    try:
        with _sqlite_connect(timeout=2) as connection:
            connection.execute("INSERT INTO translation_cache(cache_key, translated_text, created_at) VALUES (?, ?, ?) ON CONFLICT(cache_key) DO UPDATE SET translated_text=excluded.translated_text, created_at=excluded.created_at", (key, value, time.time()))
            connection.commit()
    except sqlite3.Error:
        logger.exception("Could not persist translation cache entry")


_RELEASE_FLIGHT_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""


def _claim_distributed_flights(texts: Sequence[str], cache_keys: dict[str, str], translated: dict[str, str]) -> tuple[list[str], dict[str, tuple[str, str]]]:
    client = _redis()
    if client is None:
        return list(texts), {}
    owners: list[str] = []
    held: dict[str, tuple[str, str]] = {}
    for text in texts:
        key = f"resora:translation:flight:{cache_keys[text]}"
        token = uuid.uuid4().hex
        deadline = time.monotonic() + float(os.getenv("TRANSLATION_FLIGHT_WAIT_SECONDS", "6"))
        while True:
            cached = _persistent_cache_get(cache_keys[text])
            if cached is not None:
                translated[text] = cached
                break
            try:
                if client.set(key, token, nx=True, ex=120):
                    owners.append(text)
                    held[text] = (key, token)
                    break
            except Exception:
                # Redis outage uses the existing local single-flight path.
                owners.append(text)
                break
            if time.monotonic() >= deadline:
                # Another worker is slow; translating ourselves is better than making the user wait.
                owners.append(text)
                break
            time.sleep(0.1)
    return owners, held


def _release_distributed_flights(held: dict[str, tuple[str, str]]) -> None:
    client = _redis()
    if client is None:
        return
    for key, token in held.values():
        try:
            client.eval(_RELEASE_FLIGHT_LUA, 1, key, token)
        except Exception:
            pass


def _translate_via_router(segments: Sequence[str], source: str, target: str, glossary: dict[str, str] | None, user_id: str | None = None, *, user_content: bool = True) -> list[str]:
    """AI-router translation with protected-token masking (the last step of the provider chain)."""
    masked: list[str] = []
    protected_groups: list[list[str]] = []
    for segment in segments:
        protected_text, protected = _protect(segment)
        masked.append(protected_text)
        protected_groups.append(protected)
    try:
        from app.services.ai_router import RouterUnavailable, get_default_router

        request = json.dumps({"segments": masked, "source_language": source,
                              "target_language_code": target, "glossary": glossary or {}}, ensure_ascii=False)
        started = time.perf_counter()
        response = get_default_router().complete(
            "short_translation", request,
            system="Translate each segment faithfully. Preserve all protected tokens exactly. Return only a JSON array of strings in the same order.",
            user_content=user_content,
            model_family=f"translation:{source}:{target}",
            max_tokens=min(4096, max(512, sum(len(item) for item in masked) // 2)),
            language=target,
            validator=lambda output: _valid_translation_batch(output, masked, target),
        )
        results = json.loads(response.text)
        if not isinstance(results, list) or len(results) != len(masked):
            raise TranslationUnavailable("Translation returned an invalid batch")
        restored = [_restore(str(text), tokens) for text, tokens in zip(results, protected_groups)]
        metrics = _METRICS.setdefault(response.provider, {})
        metrics["latency_ms"] = metrics.get("latency_ms", 0) + (time.perf_counter() - started) * 1000
        metrics["successes"] = metrics.get("successes", 0) + 1
        return restored
    except RouterUnavailable as exc:
        raise TranslationUnavailable("Translation is temporarily unavailable") from exc
    except TranslationIntegrityError:
        raise
    except Exception as exc:
        # Provider exceptions can echo submitted text; keep diagnostics generic.
        raise TranslationUnavailable("Translation is temporarily unavailable") from exc


# --------------------------------------------------------------------------- provider chain

# Providers that may receive private user text (uploads, typed queries). Self-hosted engines and paid
# enterprise APIs that do not train on submitted text. Override with TRANSLATION_USER_CONTENT_PROVIDERS.
_DEFAULT_USER_CONTENT_PROVIDERS = {"translator_local", "madlad", "azure", "google_cloud"}
_ROUTER_ROUTE_NAMES = {"groq", "ai_router", "router"}
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹०१२३४५६७८९০১২৩৪৫৬৭৮৯੦੧੨੩੪੫੬੭੮੯૦૧૨૩૪૫૬૭૮૯௦௧௨௩௪௫௬௭௮௯౦౧౨౩౪౫౬౭౮౯೦೧೨೩೪೫೬೭೮೯൦൧൨൩൪൫൬൭൮൯๐๑๒๓๔๕๖๗๘๙", "0123456789" * 11)
_SKIP_IF_SAME_LANGUAGE_CONFIDENCE = 0.85
_DETECT_CONFIDENCE = 0.6


def _provider_allows_user_content(name: str) -> bool:
    override = os.getenv("TRANSLATION_USER_CONTENT_PROVIDERS")
    allowed = {item.strip().lower() for item in override.split(",") if item.strip()} if override else set(_DEFAULT_USER_CONTENT_PROVIDERS)
    if name == "deepl" and "deepl" not in allowed:
        # DeepL Pro keys (not ending in ":fx") delete texts after translation.
        key = os.getenv("DEEPL_API_KEY", "")
        return bool(key) and not key.endswith(":fx")
    return name in allowed


def _fingerprint(text: str) -> str:
    """Normalise a protected item for comparison: native digits → ASCII, separators and spacing removed."""
    value = text.translate(_DIGITS).casefold()
    value = value.replace("\u066b", ".").replace("\u066c", ",")
    return re.sub(r"[\s\u00a0\u202f,.'’]", "", value)


def _protected_items_preserved(source: str, translated: str) -> bool:
    """NMT engines are not masked; instead verify numbers, DOIs, URLs, citations and maths survived intact."""
    output = _fingerprint(translated)
    for item in _PROTECTED.findall(source):
        key = _fingerprint(item)
        numeric = re.sub(r"[^0-9]", "", key)
        probe = numeric if numeric and len(numeric) == len(re.sub(r"[%a-z°]", "", key)) else key
        if probe and probe not in output:
            return False
    return True


def _chunks(provider: TranslationProvider, segments: Sequence[str]) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    size = 0
    for segment in segments:
        if current and (len(current) >= provider.limits.max_batch_size or size + len(segment) > provider.limits.max_chars_per_batch):
            chunks.append(current)
            current, size = [], 0
        current.append(segment)
        size += len(segment)
    if current:
        chunks.append(current)
    return chunks


def _call_provider(provider: TranslationProvider, segments: Sequence[str], source: str, target: str, glossary: dict[str, str] | None, user_id: str | None) -> list[str]:
    results: list[str] = []
    for chunk in _chunks(provider, segments):
        _rate_limit(provider, sum(len(item) for item in chunk), user_id)
        started = time.perf_counter()
        try:
            output = provider.translate_batch(chunk, source, target, glossary)
        except TranslationUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise _provider_error(provider.name, exc) from exc
        if len(output) != len(chunk) or any(not isinstance(item, str) or not item.strip() for item in output):
            raise _provider_error(provider.name, TranslationUnavailable("incomplete batch"))
        for original, translated in zip(chunk, output):
            if not _protected_items_preserved(original, translated):
                metrics = _METRICS.setdefault(provider.name, {})
                metrics["integrity_failures"] = metrics.get("integrity_failures", 0) + 1
                raise TranslationIntegrityError(f"{provider.name} changed protected academic text")
        _provider_success(provider.name, started)
        results.extend(output)
    return results


def _translate_group(segments: Sequence[str], source: str, target: str, glossary: dict[str, str] | None, user_id: str | None, *, user_content: bool) -> list[str]:
    """Try each configured engine in order (local first by default), then the AI router."""
    router_tried = False
    for name in _provider_order(target):
        if name in _ROUTER_ROUTE_NAMES:
            if router_tried:
                continue
            router_tried = True
            try:
                return _translate_via_router(segments, source, target, glossary, user_id, user_content=user_content)
            except TranslationUnavailable:
                continue
        provider = _PROVIDERS.get(name)
        if provider is None or (user_content and not _provider_allows_user_content(name)):
            continue
        try:
            if not provider.supports(source, target):
                continue
            return _call_provider(provider, segments, source, target, glossary, user_id)
        except TranslationUnavailable:
            metrics = _METRICS.setdefault(name, {})
            metrics["failovers"] = metrics.get("failovers", 0) + 1
            continue
    if not router_tried:
        return _translate_via_router(segments, source, target, glossary, user_id, user_content=user_content)
    raise TranslationUnavailable("Translation is temporarily unavailable")


def _translate_batch_uncached(segments: Sequence[str], source: str, target: str, glossary: dict[str, str] | None, user_id: str | None = None, *, user_content: bool = True) -> list[str]:
    """Translate a batch. With source "auto", segments are grouped by detected language so engines that need
    an explicit source language (local models) can be used, and text already in the target language is kept."""
    if source != "auto":
        return _translate_group(segments, source, target, glossary, user_id, user_content=user_content)
    groups: OrderedDict[str, list[int]] = OrderedDict()
    results: list[str | None] = [None] * len(segments)
    for index, segment in enumerate(segments):
        try:
            language, confidence = detect_language(segment)
            language = canonical_language_code(language) if language else "auto"
        except Exception:  # noqa: BLE001
            language, confidence = "auto", 0.0
        if language == target and confidence >= _SKIP_IF_SAME_LANGUAGE_CONFIDENCE:
            results[index] = segment
            continue
        groups.setdefault(language if confidence >= _DETECT_CONFIDENCE else "auto", []).append(index)
    for language, indexes in groups.items():
        translated = _translate_group([segments[i] for i in indexes], language, target, glossary, user_id, user_content=user_content)
        for index, text in zip(indexes, translated):
            results[index] = text
    return [text if text is not None else segments[index] for index, text in enumerate(results)]


def translate_batch(segments: Sequence[str], target_language: str, *, source_language: str = "auto", glossary: dict[str, str] | None = None, user_id: str | None = None, user_content: bool = True) -> list[str]:
    target = canonical_language_code(target_language)
    source = source_language if source_language == "auto" else canonical_language_code(source_language)
    normalized = [item if isinstance(item, str) else str(item) for item in segments]
    if not normalized:
        return []
    if user_content:
        private_unique = list(dict.fromkeys(normalized))
        private_results: list[str] = []
        for offset in range(0, len(private_unique), 20):
            private_results.extend(_translate_batch_uncached(private_unique[offset:offset + 20], source, target, glossary, user_id, user_content=True))
        translated = dict(zip(private_unique, private_results))
        return [translated[text] for text in normalized]
    unique = list(dict.fromkeys(normalized))
    translated_unique: dict[str, str] = {}
    missing: list[str] = []
    cache_keys: dict[str, str] = {}
    glossary_digest = hashlib.sha256(json.dumps(glossary or {}, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    memory_keys: dict[str, tuple[str, str, str, str]] = {}
    for text in unique:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        memory_key = (digest, source, target, glossary_digest)
        memory_keys[text] = memory_key
        key = f"{digest}:{source}:{target}:{_CACHE_VERSION}:{glossary_digest}"
        cache_keys[text] = key
        with _CACHE_LOCK:
            value = _CACHE.get(memory_key)
            if value is not None:
                _CACHE.move_to_end(memory_key)
        if value is None:
            value = _persistent_cache_get(key)
        if value is None:
            missing.append(text)
        else:
            translated_unique[text] = value
            metrics = _METRICS.setdefault("cache", {"hits": 0})
            metrics["hits"] = metrics.get("hits", 0) + 1
    if missing:
        owner: list[str] = []
        waiters: list[tuple[str, threading.Event]] = []
        with _CACHE_LOCK:
            for text in missing:
                cache_key = memory_keys[text]
                event = _INFLIGHT.get(cache_key)
                if event is None:
                    event = threading.Event()
                    _INFLIGHT[cache_key] = event
                    owner.append(text)
                else:
                    waiters.append((text, event))
        if owner:
            local_owner = list(owner)
            held_flights: dict[str, tuple[str, str]] = {}
            try:
                owner, held_flights = _claim_distributed_flights(owner, cache_keys, translated_unique)
                with _CACHE_LOCK:
                    for text, value in translated_unique.items():
                        _CACHE[memory_keys[text]] = value
                outputs: list[str] = []
                for index in range(0, len(owner), 20):
                    chunk = owner[index:index + 20]
                    try:
                        outputs.extend(_translate_batch_uncached(chunk, source, target, glossary, user_id, user_content=False))
                    except TranslationIntegrityError:
                        # One segment confused every engine; translate the rest individually.
                        if len(chunk) == 1:
                            raise
                        outputs.extend([_translate_batch_uncached([text], source, target, glossary, user_id, user_content=False)[0] for text in chunk])
                for text, translated in zip(owner, outputs):
                    memory_key = memory_keys[text]
                    with _CACHE_LOCK:
                        _CACHE[memory_key] = translated
                        _CACHE.move_to_end(memory_key)
                        while len(_CACHE) > _CACHE_LIMIT:
                            _CACHE.popitem(last=False)
                    _persistent_cache_set(cache_keys[text], translated)
                    translated_unique[text] = translated
            except Exception as exc:
                for _, event in waiters:
                    event.set()
                if isinstance(exc, TranslationUnavailable):
                    raise
                raise TranslationUnavailable("Translation is temporarily unavailable") from exc
            finally:
                _release_distributed_flights(held_flights)
                with _CACHE_LOCK:
                    for text in local_owner:
                        cache_key = memory_keys[text]
                        event = _INFLIGHT.pop(cache_key, None)
                        if event:
                            event.set()
        for text, event in waiters:
            event.wait(timeout=8)
            with _CACHE_LOCK:
                value = _CACHE.get(memory_keys[text])
            if value is None:
                value = _persistent_cache_get(cache_keys[text])
            if value is None:
                raise TranslationUnavailable("Translation is temporarily unavailable")
            translated_unique[text] = value
    return [translated_unique[text] for text in normalized]


def translate_text(text: str, target_language: str, *, source_language: str = "auto", glossary: dict[str, str] | None = None, user_id: str | None = None, user_content: bool = True) -> str:
    if not text or not text.strip():
        return text
    if target_language == "en" and source_language in {"en", "auto"}:
        return text
    return translate_batch([text], target_language, source_language=source_language, glossary=glossary, user_id=user_id, user_content=user_content)[0]


def translate_paper_text(title: str, abstract: str | None, target_language: str, user_id: str | None = None) -> tuple[str | None, str | None]:
    segments = [text for text in (title, abstract or "") if text.strip()]
    if not segments:
        return None, None
    translated = iter(translate_batch(segments, target_language, user_id=user_id, user_content=False))
    return (next(translated) if title.strip() else None, next(translated) if (abstract or "").strip() else None)


def _retry_status_write(job: dict[str, object]) -> None:
    job_id = str(job["job_id"])
    client = _redis()
    if client is not None:
        try:
            client.set(f"resora:translation:retry:status:{job_id}", json.dumps(job, ensure_ascii=False), ex=30 * 24 * 3600)
            return
        except Exception:
            pass
    _RETRY_STATUS_LOCAL[job_id] = dict(job)
    if len(_RETRY_STATUS_LOCAL) > 2048:
        _RETRY_STATUS_LOCAL.pop(next(iter(_RETRY_STATUS_LOCAL)))


def get_translation_retry_status(job_id: str, user_id: str) -> dict[str, object] | None:
    client = _redis()
    if client is not None:
        try:
            value = client.get(f"resora:translation:retry:status:{job_id}")
            job = json.loads(value) if value else None
        except Exception:
            job = None
    else:
        job = _RETRY_STATUS_LOCAL.get(job_id)
    if not isinstance(job, dict) or job.get("user_id") != user_id:
        return None
    return {key: value for key, value in job.items() if key not in {"title", "abstract"}}


def _run_translation_retry(job: dict[str, object]) -> None:
    job["status"] = "retrying"
    for attempt in range(1, 4):
        job["attempts"] = attempt
        job["updated_at"] = time.time()
        _retry_status_write(job)
        try:
            if attempt > 1:
                base = max(0.0, min(float(os.getenv("TRANSLATION_BACKGROUND_RETRY_SECONDS", "3")), 60.0))
                time.sleep(min(base * (2 ** (attempt - 2)), 60.0))
            title, abstract = translate_paper_text(
                str(job["title"]), str(job.get("abstract") or ""), str(job["target_language"]),
                user_id=str(job.get("user_id") or "anonymous"),
            )
            job.update({"status": "completed", "translated_title": title, "translated_abstract": abstract, "updated_at": time.time()})
            _retry_status_write(job)
            with _RETRY_LOCK:
                _RETRY_PENDING.discard(str(job.get("identity", "")))
            return
        except Exception:
            logger.info("Background translation retry attempt failed", extra={"job_id": job["job_id"], "attempt": attempt})
    job.update({"status": "failed", "updated_at": time.time()})
    _retry_status_write(job)
    with _RETRY_LOCK:
        _RETRY_PENDING.discard(str(job.get("identity", "")))


def _consume_translation_retry_queue() -> None:
    global _RETRY_WORKER_RUNNING
    queue_key = "resora:translation:retry:queue"
    idle_polls = 0
    try:
        while True:
            client = _redis()
            if client is None:
                return
            try:
                payload = client.lpop(queue_key)
            except Exception:
                return
            if payload:
                idle_polls = 0
                try:
                    _run_translation_retry(json.loads(payload))
                except Exception:
                    logger.exception("Could not process durable translation retry")
                continue
            idle_polls += 1
            if idle_polls < 4:
                time.sleep(0.25)
                continue
            with _RETRY_LOCK:
                try:
                    if client.llen(queue_key):
                        continue
                except Exception:
                    pass
                _RETRY_WORKER_RUNNING = False
                return
    finally:
        with _RETRY_LOCK:
            _RETRY_WORKER_RUNNING = False


def start_translation_retry_worker() -> None:
    global _RETRY_WORKER_RUNNING
    if _redis() is None:
        return
    with _RETRY_LOCK:
        if _RETRY_WORKER_RUNNING:
            return
        _RETRY_WORKER_RUNNING = True
    try:
        _RETRY_EXECUTOR.submit(_consume_translation_retry_queue)
    except RuntimeError:
        with _RETRY_LOCK:
            _RETRY_WORKER_RUNNING = False


def schedule_translation_retry(title: str, abstract: str | None, target_language: str, *, user_id: str | None = None, paper_id: str | None = None) -> str | None:
    """Persist a bounded retry job and return its user-scoped polling ID."""
    if not title.strip() and not (abstract or "").strip():
        return None
    owner = (user_id or "anonymous").strip() or "anonymous"
    # Per user: a job ID is only readable by its owner, so sharing one across users would hide the result.
    identity = hashlib.sha256(f"{owner}\0{target_language}\0{title}\0{abstract or ''}".encode("utf-8")).hexdigest()
    now = time.monotonic()
    client = _redis()
    job_id = uuid.uuid4().hex
    with _RETRY_LOCK:
        if identity in _RETRY_PENDING or now - _RETRY_LAST_SCHEDULED.get(identity, 0.0) < 60.0 or len(_RETRY_PENDING) >= 128:
            return _RETRY_DEDUPE_LOCAL.get(identity)
        if client is not None:
            try:
                claimed = client.set(f"resora:translation:retry:dedupe:{identity}", job_id, nx=True, ex=60)
                if not claimed:
                    return str(client.get(f"resora:translation:retry:dedupe:{identity}") or "") or None
            except Exception:
                client = None
        _RETRY_PENDING.add(identity)
        _RETRY_LAST_SCHEDULED[identity] = now
        _RETRY_DEDUPE_LOCAL[identity] = job_id
        while len(_RETRY_LAST_SCHEDULED) > _RETRY_BOOKKEEPING_LIMIT:
            _RETRY_LAST_SCHEDULED.pop(next(iter(_RETRY_LAST_SCHEDULED)))
        while len(_RETRY_DEDUPE_LOCAL) > _RETRY_BOOKKEEPING_LIMIT:
            _RETRY_DEDUPE_LOCAL.pop(next(iter(_RETRY_DEDUPE_LOCAL)))
    job: dict[str, object] = {
        "job_id": job_id, "identity": identity, "paper_id": paper_id,
        "user_id": owner,
        "target_language": target_language, "title": title, "abstract": abstract or "",
        "status": "queued", "attempts": 0, "created_at": time.time(), "updated_at": time.time(),
    }
    _retry_status_write(job)
    if client is not None:
        try:
            client.rpush("resora:translation:retry:queue", json.dumps(job, ensure_ascii=False))
            start_translation_retry_worker()
            return job_id
        except Exception:
            logger.exception("Could not enqueue durable translation retry; using local worker")

    def retry() -> None:
        try:
            _run_translation_retry(job)
        finally:
            with _RETRY_LOCK:
                _RETRY_PENDING.discard(identity)

    try:
        _RETRY_EXECUTOR.submit(retry)
    except RuntimeError:
        with _RETRY_LOCK:
            _RETRY_PENDING.discard(identity)
    return job_id


def clear_translation_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()
