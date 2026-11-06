from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import sqlite3
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Iterator, Mapping

from .providers import (
    AIResponse,
    OpenAICompatibleProvider,
    OpenRouterProvider,
    ProviderFailure,
)

logger = logging.getLogger(__name__)

_RESERVE_BUDGET_LUA = """
local requests = tonumber(ARGV[1])
local tokens = tonumber(ARGV[2])
local rpm = tonumber(ARGV[3])
local tpm = tonumber(ARGV[4])
local rpd = tonumber(ARGV[5])
local tpd = tonumber(ARGV[6])
local rpd_switch = rpd > 0 and math.max(1, math.floor(rpd * 0.9)) or 0
local tpd_switch = tpd > 0 and math.max(1, math.floor(tpd * 0.9)) or 0
local minute_requests = tonumber(redis.call('GET', KEYS[1]) or '0')
local minute_tokens = tonumber(redis.call('GET', KEYS[2]) or '0')
local day_requests = tonumber(redis.call('GET', KEYS[3]) or '0')
local day_tokens = tonumber(redis.call('GET', KEYS[4]) or '0')
local live_requests = redis.call('GET', KEYS[5])
local live_tokens = redis.call('GET', KEYS[6])
if (rpm > 0 and minute_requests + requests > rpm) or (tpm > 0 and minute_tokens + tokens > tpm) or
   (rpd_switch > 0 and day_requests + requests > rpd_switch) or (tpd_switch > 0 and day_tokens + tokens > tpd_switch) or
   (live_requests and tonumber(live_requests) < requests) or (live_tokens and tonumber(live_tokens) < tokens) then return 0 end
redis.call('INCRBY', KEYS[1], requests); redis.call('INCRBY', KEYS[2], tokens)
redis.call('INCRBY', KEYS[3], requests); redis.call('INCRBY', KEYS[4], tokens)
if live_requests then redis.call('DECRBY', KEYS[5], requests) end
if live_tokens then redis.call('DECRBY', KEYS[6], tokens) end
redis.call('EXPIRE', KEYS[1], 120); redis.call('EXPIRE', KEYS[2], 120)
redis.call('EXPIRE', KEYS[3], 172800); redis.call('EXPIRE', KEYS[4], 172800)
return 1
"""


class RouterUnavailable(RuntimeError):
    """Raised when no eligible provider can safely complete a task."""


@dataclass(frozen=True)
class Route:
    provider: str
    model: str
    weight: int = 1
    max_input_chars: int = 12000
    daily_request_limit: int = 0
    language_weight: int = 0
    languages: tuple[str, ...] = ()


class RouterCache:
    """Redis hot cache plus local SQLite persistence. Only hashed keys are stored."""

    def __init__(self, *, ttl_seconds: int = 86400, path: str | None = None, redis_client=None):
        self.ttl_seconds = max(1, ttl_seconds)
        self.path = Path(path or os.getenv("AI_ROUTER_CACHE_PATH", "storage/ai_router_cache.sqlite3"))
        self.redis = redis_client
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.path) as db:
                db.execute("CREATE TABLE IF NOT EXISTS ai_cache (cache_key TEXT PRIMARY KEY, value TEXT NOT NULL, expires REAL NOT NULL)")
        except OSError:
            logger.warning("AI router persistent cache unavailable")

    def get(self, key: str) -> AIResponse | None:
        if self.redis:
            try:
                raw = self.redis.get("resora:ai:cache:" + key)
                if raw:
                    value = json.loads(raw)
                    return AIResponse(**value)
            except Exception:
                logger.debug("AI router Redis cache read failed")
        try:
            with sqlite3.connect(self.path) as db:
                row = db.execute("SELECT value FROM ai_cache WHERE cache_key=? AND expires>?", (key, time.time())).fetchone()
            if row:
                return AIResponse(**json.loads(row[0]))
        except (OSError, sqlite3.Error, ValueError, TypeError):
            logger.debug("AI router SQLite cache read failed")
        return None

    def set(self, key: str, response: AIResponse) -> None:
        value = json.dumps({"provider": response.provider, "model": response.model, "text": response.text,
                            "usage": response.usage, "headers": {}, "latency_ms": response.latency_ms})
        if self.redis:
            try:
                self.redis.setex("resora:ai:cache:" + key, self.ttl_seconds, value)
            except Exception:
                logger.debug("AI router Redis cache write failed")
        try:
            with sqlite3.connect(self.path) as db:
                db.execute("INSERT OR REPLACE INTO ai_cache(cache_key,value,expires) VALUES(?,?,?)",
                           (key, value, time.time() + self.ttl_seconds))
        except (OSError, sqlite3.Error):
            logger.debug("AI router SQLite cache write failed")


class AIRouter:
    """Weighted task router with privacy filtering, cache, budgets and provider cooldowns."""

    def __init__(self, providers: Mapping[str, object], routes: Mapping[str, Iterable[Route]], *,
                 cache: RouterCache | None = None, free_models_only: bool = True,
                 max_concurrency: int = 4, failure_threshold: int = 2,
                 clock: Callable[[], float] = time.monotonic,
                 daily_usage: dict[str, int] | None = None,
                 redis_client=None, provider_limits: Mapping[str, Mapping[str, int]] | None = None):
        self.providers = dict(providers)
        self.routes = {name: tuple(items) for name, items in routes.items()}
        self.cache = cache or RouterCache()
        self.free_models_only = free_models_only
        self.failure_threshold = max(1, failure_threshold)
        self.clock = clock
        self.daily_usage = daily_usage if daily_usage is not None else defaultdict(int)
        self.redis = redis_client
        self.provider_limits = {name: dict(limits) for name, limits in (provider_limits or {}).items()}
        self._usage_day = datetime.now(timezone.utc).date()
        self._semaphore = threading.BoundedSemaphore(max(1, max_concurrency))
        self._lock = threading.RLock()
        self._cursor: dict[str, int] = defaultdict(int)
        self._failures: dict[str, int] = defaultdict(int)
        self._cooldown_until: dict[str, float] = defaultdict(float)
        self._metrics: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._probe_status: dict[str, dict[str, object]] = {}

    def _expanded(self, task: str) -> list[Route]:
        entries: list[Route] = []
        for route in self.routes.get(task, ()):
            provider = self.providers.get(route.provider)
            if provider is None or not getattr(provider, "available", True):
                continue
            if isinstance(provider, OpenRouterProvider) and route.model in {"auto-free", "auto-qwen-free", "auto-qwen-free-judge"}:
                try:
                    models = provider.list_free_models()
                except ProviderFailure:
                    self._metrics[route.provider]["model_discovery_errors"] += 1
                    continue
                selected = models
                if route.model.startswith("auto-qwen-free"):
                    selected = [model for model in models if "qwen" in (model.id + " " + model.name).casefold()]
                    if route.model == "auto-qwen-free-judge":
                        # Use the largest distinct free Qwen for judging; never reuse the translation model.
                        selected = sorted(selected, key=lambda item: (item.context_length or 0, item.id), reverse=True)
                        translator_model = min(selected, key=lambda item: (item.context_length or 0, item.id)).id if selected else None
                        selected = [model for model in selected if model.id != translator_model][:1]
                    else:
                        # Keep translation on one small Qwen model so the judge pool can be distinct.
                        selected = sorted(selected, key=lambda item: (item.context_length or 0, item.id))[:1]
                entries.extend(Route(route.provider, model.id, route.weight, route.max_input_chars,
                                     route.daily_request_limit, route.language_weight, route.languages) for model in selected)
            else:
                entries.append(route)
        return entries

    def _candidates(self, task: str, *, user_content: bool, prompt_length: int) -> list[Route]:
        entries = self._expanded(task)
        now = self.clock()
        eligible = []
        for route in entries:
            provider = self.providers[route.provider]
            if prompt_length > route.max_input_chars:
                continue
            if user_content and not getattr(provider, "allow_user_content", False):
                self._metrics[route.provider]["privacy_blocks"] += 1
                continue
            if self._is_cooling(route.provider, now):
                continue
            if route.daily_request_limit and self._daily_used(route.provider) >= int(route.daily_request_limit * 0.9):
                continue
            if self.free_models_only and route.provider == "openrouter" and not route.model.endswith(":free"):
                self._metrics[route.provider]["paid_model_blocks"] += 1
                continue
            eligible.append(route)
        return eligible

    def _is_cooling(self, provider: str, now: float) -> bool:
        if self._cooldown_until[provider] > now:
            return True
        if self.redis is not None:
            try:
                return bool(self.redis.exists(f"resora:ai:circuit:{provider}"))
            except Exception:
                logger.debug("AI router Redis circuit read failed", extra={"provider": provider})
        return False

    def _set_circuit(self, provider: str, seconds: float) -> None:
        self._cooldown_until[provider] = self.clock() + seconds
        if self.redis is not None:
            try:
                self.redis.setex(f"resora:ai:circuit:{provider}", max(1, int(seconds)), "open")
            except Exception:
                logger.debug("AI router Redis circuit update failed", extra={"provider": provider})

    def _clear_circuit(self, provider: str) -> None:
        self._cooldown_until[provider] = 0
        if self.redis is not None:
            try:
                self.redis.delete(f"resora:ai:circuit:{provider}")
            except Exception:
                logger.debug("AI router Redis circuit clear failed", extra={"provider": provider})

    def _daily_used(self, provider: str) -> int:
        today = datetime.now(timezone.utc).date()
        with self._lock:
            if today != self._usage_day:
                self.daily_usage.clear()
                self._usage_day = today
            return int(self.daily_usage.get(provider, 0))

    def _reserve_provider_budget(self, provider: str, prompt: str, system: str, max_tokens: int) -> bool:
        limits = self.provider_limits.get(provider, {})
        if not any(int(limits.get(key, 0) or 0) > 0 for key in ("rpm", "tpm", "rpd", "tpd")):
            return True
        if self.redis is None:
            return False  # Configured shared quotas fail closed without Redis.
        now = datetime.now(timezone.utc)
        prefix = f"resora:ai:budget:{provider}"
        minute = now.strftime("%Y%m%d%H%M")
        day = now.strftime("%Y%m%d")
        keys = [f"{prefix}:minute:req:{minute}", f"{prefix}:minute:tokens:{minute}",
                f"{prefix}:day:req:{day}", f"{prefix}:day:tokens:{day}"]
        keys.extend([f"{prefix}:live:requests", f"{prefix}:live:tokens"])
        token_reservation = max(1, (len(prompt) + len(system) + 3) // 4) + max_tokens
        try:
            return bool(self.redis.eval(
                _RESERVE_BUDGET_LUA, 6, *keys, 1, token_reservation,
                int(limits.get("rpm", 0) or 0), int(limits.get("tpm", 0) or 0),
                int(limits.get("rpd", 0) or 0), int(limits.get("tpd", 0) or 0),
            ))
        except Exception:
            logger.warning("AI router shared quota reservation failed", extra={"provider": provider})
            return False

    def _ordered(self, task: str, candidates: list[Route], language: str | None = None) -> list[Route]:
        if not candidates:
            return []
        normalized_language = (language or "").replace("_", "-").casefold()
        weighted = [route for route in candidates for _ in range(max(1, route.weight + (route.language_weight if any(normalized_language == item.casefold() for item in route.languages) else 0)))]
        with self._lock:
            start = self._cursor[task] % len(weighted)
            self._cursor[task] += 1
        rotated = weighted[start:] + weighted[:start]
        result, seen = [], set()
        for route in rotated:
            ident = (route.provider, route.model)
            if ident not in seen:
                seen.add(ident)
                result.append(route)
        return result

    @staticmethod
    def _cache_key(task: str, prompt: str, model_family: str, prompt_version: str) -> str:
        normalized = " ".join(prompt.split()).casefold()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return hashlib.sha256(f"{task}:{model_family}:{prompt_version}:{digest}".encode()).hexdigest()

    def complete(self, task: str, prompt: str, *, system: str = "", user_content: bool = False,
                 model_family: str = "default", prompt_version: str = "v1", max_tokens: int = 1024,
                 validator: Callable[[str], bool] | None = None, language: str | None = None) -> AIResponse:
        routes = self.routes.get(task)
        if routes is None:
            raise RouterUnavailable("This AI task is not configured.")
        family = model_family or ",".join(sorted({route.provider for route in routes}))
        cache_key = self._cache_key(task, prompt, family, prompt_version)
        # Do not persist user supplied content, even as a model response cache key.
        # This prevents private PDF/chat material from reaching Redis or SQLite.
        cached = self.cache.get(cache_key) if not user_content else None
        if cached:
            cached_provider = self.providers.get(cached.provider)
            if user_content and not getattr(cached_provider, "allow_user_content", False):
                cached = None
        if cached:
            self._metrics[cached.provider]["cache_hits"] += 1
            return cached
        candidates = self._ordered(task, self._candidates(task, user_content=user_content, prompt_length=len(prompt)), language)[:3]
        if not candidates:
            raise RouterUnavailable("This AI task is temporarily unavailable for the current privacy and provider settings.")
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        errors = []
        validation_attempts = 0
        rejected_provider: str | None = None
        for route in candidates:
            if rejected_provider and route.provider == rejected_provider:
                continue
            provider = self.providers[route.provider]
            try:
                if not self._reserve_provider_budget(route.provider, prompt, system, max_tokens):
                    self._metrics[route.provider]["budget_blocks"] += 1
                    errors.append("budget")
                    continue
                with self._semaphore:
                    response = provider.complete(route.model, messages, max_tokens=max_tokens)
                if not response.text.strip() or (validator and not validator(response.text)):
                    self._metrics[route.provider]["validation_failures"] += 1
                    errors.append("validation")
                    validation_attempts += 1
                    rejected_provider = route.provider
                    if validation_attempts >= 2:
                        break
                    continue
                with self._lock:
                    self._failures[route.provider] = 0
                    self._clear_circuit(route.provider)
                    self.daily_usage[route.provider] = self.daily_usage.get(route.provider, 0) + 1
                    self._metrics[route.provider]["calls"] += 1
                    self._metrics[route.provider]["tokens"] += response.usage
                    self._record_rate_headers(route.provider, response.headers)
                    self._metrics[route.provider]["latency_ms_total"] += response.latency_ms
                    samples = self._latencies[route.provider]
                    samples.append(response.latency_ms)
                    del samples[:-2048]
                    if errors:
                        self._metrics[route.provider]["failovers"] += 1
                if not user_content:
                    self.cache.set(cache_key, response)
                return response
            except ProviderFailure as exc:
                errors.append("provider_failure")
                with self._lock:
                    self._failures[route.provider] += 1
                    self._metrics[route.provider]["errors"] += 1
                    if exc.status_code == 429:
                        self._metrics[route.provider]["rate_limits"] += 1
                    if self._failures[route.provider] >= self.failure_threshold:
                        base = exc.retry_after or min(60, 2 ** self._failures[route.provider])
                        self._set_circuit(route.provider, base + random.random())
                        self._metrics[route.provider]["cooldowns"] += 1
            except Exception:
                # Do not log exception text; provider SDKs can include request content.
                errors.append("internal_provider_failure")
                self._metrics[route.provider]["errors"] += 1
                logger.warning("AI router provider call failed", extra={"provider": route.provider, "task": task})
        self._metrics["router"]["exhausted_requests"] += 1
        raise RouterUnavailable("AI service is temporarily unavailable. Please retry.") from None

    def stream(self, task: str, prompt: str, *, system: str = "", user_content: bool = False,
               max_tokens: int = 1024) -> Iterator[str]:
        """Stream from the weighted pool; fail over only before any text was yielded."""
        if task not in self.routes:
            raise RouterUnavailable("This AI task is not configured.")
        candidates = self._ordered(task, self._candidates(task, user_content=user_content,
                                                          prompt_length=len(prompt)))[:3]
        if not candidates:
            raise RouterUnavailable("This AI task is temporarily unavailable for the current privacy and provider settings.")
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        for route in candidates:
            provider = self.providers[route.provider]
            stream_fn = getattr(provider, "stream", None)
            if stream_fn is None:
                continue
            emitted = False
            try:
                if not self._reserve_provider_budget(route.provider, prompt, system, max_tokens):
                    self._metrics[route.provider]["budget_blocks"] += 1
                    continue
                with self._semaphore:
                    for chunk in stream_fn(route.model, messages, max_tokens=max_tokens):
                        if chunk:
                            emitted = True
                            yield chunk
                self._metrics[route.provider]["stream_calls"] += 1
                self._failures[route.provider] = 0
                self._clear_circuit(route.provider)
                return
            except ProviderFailure as exc:
                self._metrics[route.provider]["errors"] += 1
                if emitted:
                    raise RouterUnavailable("The response stream was interrupted. Please retry.") from None
                with self._lock:
                    self._failures[route.provider] += 1
                    if exc.status_code == 429:
                        self._metrics[route.provider]["rate_limits"] += 1
                    if self._failures[route.provider] >= self.failure_threshold:
                        delay = exc.retry_after or min(60, 2 ** self._failures[route.provider])
                        self._set_circuit(route.provider, delay + random.random())
            except Exception:
                self._metrics[route.provider]["errors"] += 1
                if emitted:
                    raise RouterUnavailable("The response stream was interrupted. Please retry.") from None
                self._failures[route.provider] += 1
                if self._failures[route.provider] >= self.failure_threshold:
                    self._set_circuit(route.provider, min(60, 2 ** self._failures[route.provider]) + random.random())
        raise RouterUnavailable("AI service is temporarily unavailable. Please retry.") from None

    def metrics(self) -> dict[str, dict[str, float]]:
        with self._lock:
            snapshot = {name: dict(values) for name, values in self._metrics.items()}
            for name, values in snapshot.items():
                samples = sorted(self._latencies.get(name, ()))
                if samples:
                    values["latency_p50_ms"] = samples[int((len(samples) - 1) * 0.50)]
                    values["latency_p95_ms"] = samples[int((len(samples) - 1) * 0.95)]
            return snapshot

    def _record_rate_headers(self, provider: str, headers: Mapping[str, str]) -> None:
        """Keep only numeric quota telemetry; never retain arbitrary response headers."""
        normalized = {str(key).casefold(): str(value) for key, value in headers.items()}
        for suffix, metric in (("remaining-requests", "requests_remaining"),
                               ("remaining-tokens", "tokens_remaining")):
            value = next((raw for key, raw in normalized.items() if key.endswith(suffix)), None)
            if value is not None:
                try:
                    remaining = max(0, float(value))
                    self._metrics[provider][metric] = remaining
                    if self.redis is not None:
                        key_suffix = "requests" if metric == "requests_remaining" else "tokens"
                        self.redis.setex(f"resora:ai:budget:{provider}:live:{key_suffix}", 60, int(remaining))
                except ValueError:
                    continue
                except Exception:
                    logger.debug("AI router live quota header update failed", extra={"provider": provider})

    def provider_health(self) -> dict[str, dict[str, object]]:
        now = self.clock()
        status = {}
        for name, provider in self.providers.items():
            cooldown = max(0, self._cooldown_until[name] - now)
            if cooldown == 0 and self.redis is not None:
                try:
                    redis_ttl = self.redis.ttl(f"resora:ai:circuit:{name}")
                    cooldown = max(0, float(redis_ttl))
                except Exception:
                    pass
            limits = self.provider_limits.get(name, {})
            daily_limit = int(limits.get("rpd", 0) or 0)
            used = self._daily_used(name)
            remaining = max(0, daily_limit - used) if daily_limit else None
            status[name] = {"configured": bool(getattr(provider, "available", True)),
                            "healthy": cooldown <= 0,
                            "cooldown_seconds": round(cooldown, 1),
                            "daily_quota": {"limit": daily_limit or None, "used": used, "remaining": remaining},
                            "last_probe": dict(self._probe_status.get(name, {})),
                            "metrics": dict(self._metrics[name])}
        return status

    def probe_provider(self, name: str) -> dict[str, object]:
        """Run a tiny non-user prompt against one configured hosted provider, respecting quota."""
        provider = self.providers.get(name)
        if provider is None or not getattr(provider, "available", True):
            result = {"configured": False, "healthy": False, "reason": "missing_key"}
            self._probe_status[name] = result
            return result
        limits = self.provider_limits.get(name, {})
        daily_limit = int(limits.get("rpd", 0) or 0)
        used = self._daily_used(name)
        if daily_limit and used >= int(daily_limit * 0.9):
            self._metrics[name]["probe_skipped_quota"] += 1
            result = {"configured": True, "healthy": None, "reason": "near_daily_limit", "checked_at": datetime.now(timezone.utc).isoformat()}
            self._probe_status[name] = result
            return result
        routes = [route for items in self.routes.values() for route in items if route.provider == name]
        route = next((item for item in routes if item.model not in {"auto-free", "auto-qwen-free", "auto-qwen-free-judge"}), None)
        if route is None and isinstance(provider, OpenRouterProvider):
            try:
                model = next(iter(provider.list_free_models()), None)
            except ProviderFailure:
                model = None
            if model is not None:
                route = Route(name, model.id)
        if route is None:
            result = {"configured": True, "healthy": None, "reason": "no_probe_model", "checked_at": datetime.now(timezone.utc).isoformat()}
            self._probe_status[name] = result
            return result
        try:
            if not self._reserve_provider_budget(name, "Reply OK", "Health probe", 1):
                self._metrics[name]["probe_skipped_quota"] += 1
                result = {"configured": True, "healthy": None, "reason": "quota_unavailable", "checked_at": datetime.now(timezone.utc).isoformat()}
                self._probe_status[name] = result
                return result
            with self._semaphore:
                probe_fn = getattr(provider, "probe", None)
                if probe_fn is not None:
                    probe_fn()
                else:
                    response = provider.complete(route.model, [{"role": "user", "content": "Reply OK"}], max_tokens=1)
                    if not response.text.strip():
                        raise ProviderFailure("empty health probe response")
            self.daily_usage[name] = self.daily_usage.get(name, 0) + 1
            self._metrics[name]["health_probes"] += 1
            result = {"configured": True, "healthy": True, "reason": "ok", "checked_at": datetime.now(timezone.utc).isoformat()}
            self._probe_status[name] = result
            return result
        except Exception as exc:
            self._metrics[name]["health_probe_failures"] += 1
            # Avoid provider exception text, which may contain request data.
            result = {"configured": True, "healthy": False, "reason": "provider_error", "error_type": type(exc).__name__, "checked_at": datetime.now(timezone.utc).isoformat()}
            self._probe_status[name] = result
            return result


def default_providers() -> dict[str, object]:
    """Only official compatible endpoints; a missing credential makes a provider unavailable."""
    from app.core.config import settings
    specs = {
        "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", False),
        "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", True),
        "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY", False),
        "cerebras": ("https://api.cerebras.ai/v1", "CEREBRAS_API_KEY", False),
        "siliconflow": ("https://api.siliconflow.com/v1", "SILICONFLOW_API_KEY", False),
        "modelscope": ("https://api-inference.modelscope.cn/v1", "MODELSCOPE_TOKEN", False),
    }
    result: dict[str, object] = {}
    for name, (url, key_env, allow_user) in specs.items():
        # Pydantic settings may have loaded values from .env; export only to this process.
        configured = getattr(settings, key_env.lower(), None)
        if configured and not os.getenv(key_env):
            os.environ[key_env] = str(configured)
        result[name] = OpenAICompatibleProvider(name, base_url=url, key_env=key_env,
                                                allow_user_content=allow_user,
                                                timeout=float(os.getenv("AI_ROUTER_TIMEOUT_SECONDS", "30")))
    configured = getattr(settings, "openrouter_api_key", None)
    if configured and not os.getenv("OPENROUTER_API_KEY"):
        os.environ["OPENROUTER_API_KEY"] = str(configured)
    result["openrouter"] = OpenRouterProvider(timeout=float(os.getenv("AI_ROUTER_TIMEOUT_SECONDS", "30")))
    from .translation_adapters import translation_engine_providers

    result.update(translation_engine_providers())
    return result


@lru_cache(maxsize=1)
def get_default_router() -> AIRouter:
    from app.core.config import settings
    try:
        import redis
        redis_client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=0.15, socket_timeout=0.15)
        redis_client.ping()
    except Exception:
        redis_client = None
    cache = RouterCache(ttl_seconds=settings.ai_router_cache_ttl_seconds,
                        path=settings.ai_router_cache_path, redis_client=redis_client)
    try:
        provider_limits = json.loads(settings.ai_router_provider_limits)
        if not isinstance(provider_limits, dict):
            provider_limits = {}
    except (ValueError, TypeError):
        provider_limits = {}
    return AIRouter(default_providers(), load_routes(settings.ai_router_routes_path), cache=cache,
                    free_models_only=settings.ai_router_free_models_only,
                    max_concurrency=settings.ai_router_max_concurrency, redis_client=redis_client,
                    provider_limits=provider_limits)


def load_routes(path: str | None = None) -> dict[str, tuple[Route, ...]]:
    route_path = Path(path or os.getenv("AI_ROUTER_ROUTES_PATH", "apps/api/app/services/ai_router/routes.json"))
    if not route_path.exists():
        route_path = Path(__file__).with_name("routes.json")
    payload = json.loads(route_path.read_text(encoding="utf-8"))
    return {task: tuple(Route(**entry) for entry in entries) for task, entries in payload.items()}
