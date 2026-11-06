from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from app.schemas.search import SearchRequest
from app.services.language.config import (
    canonical_language_code,
    detect_language,
    language_profile,
)
from app.services.search import translation
from app.services.search.translation import (
    TranslationUnavailable,
    clear_translation_cache,
    translate_text,
)


def test_supported_language_aliases_and_rtl_profiles():
    assert canonical_language_code("zh-TW") == "zh-Hant"
    assert canonical_language_code("pa") == "pa-Arab"
    assert language_profile("ur").direction == "rtl"
    assert detect_language("\u06cc\u06c1 \u0627\u06cc\u06a9 \u062a\u062d\u0642\u06cc\u0642\u06cc \u0633\u0648\u0627\u0644 \u06c1\u06d2")[0] == "ur"


def test_search_request_validates_language_fields():
    request = SearchRequest(query="machine learning", query_language="auto", paper_language="ur", target_language="zh-CN", translate_results=True)
    assert request.query_language == "auto"
    assert request.paper_language == "ur"
    assert request.target_language == "zh-Hans"
    assert request.to_filters().language == "ur"


def test_unavailable_translation_retries_once_in_background(monkeypatch):
    calls = []

    class ImmediateExecutor:
        def submit(self, function):
            function()

    monkeypatch.setattr(translation, "_RETRY_EXECUTOR", ImmediateExecutor())
    monkeypatch.setattr(translation.time, "sleep", lambda _seconds: None)
    def translate(*args, **_kwargs):
        calls.append(args)
        return "translated title", "translated abstract"

    monkeypatch.setattr(translation, "translate_paper_text", translate)
    monkeypatch.setenv("TRANSLATION_BACKGROUND_RETRY_SECONDS", "0")
    title = "retry-fixture-unique-title-2026"
    job_id = translation.schedule_translation_retry(title, "Abstract", "ur", user_id="retry-user", paper_id="paper-1")
    translation.schedule_translation_retry(title, "Abstract", "ur", user_id="retry-user", paper_id="paper-1")
    assert calls == [(title, "Abstract", "ur")]
    assert job_id
    status = translation.get_translation_retry_status(job_id, "retry-user")
    assert status and status["status"] == "completed" and status["paper_id"] == "paper-1"
    assert translation.get_translation_retry_status(job_id, "different-user") is None


def test_redis_translation_quota_reservation_is_atomic_and_includes_user_limit(monkeypatch):
    class FakeRedis:
        result = 0
        call = None

        def eval(self, *args):
            self.call = args
            return self.result

    client = FakeRedis()
    monkeypatch.setattr(translation, "_redis", lambda: client)
    monkeypatch.setenv("TRANSLATION_MONTHLY_CHARACTER_BUDGETS", '{"fixture":1000}')
    monkeypatch.setenv("TRANSLATION_DAILY_CHARACTER_BUDGETS", '{"fixture":200}')
    monkeypatch.setenv("TRANSLATION_USER_DAILY_CHARACTER_LIMIT", "80")
    assert translation._reserve_translation_usage("fixture", 25, "quota-user") is False
    script, key_count, month_key, day_key, user_key, chars, month_limit, day_limit, user_limit = client.call
    assert "INCRBY" in script and "GET" in script
    assert key_count == 3 and "usage:fixture:" in month_key and "usage:fixture:" in day_key
    assert "user-usage:quota-user:" in user_key
    assert (chars, month_limit, day_limit, user_limit) == (25, 1000, 200, 80)
    client.result = 1
    assert translation._reserve_translation_usage("fixture", 25, "quota-user") is True


def test_process_local_user_daily_quota_fallback(monkeypatch):
    translation._USER_BUDGET_USAGE.clear()
    monkeypatch.setattr(translation, "_redis", lambda: None)
    monkeypatch.setenv("TRANSLATION_USER_DAILY_CHARACTER_LIMIT", "10")
    assert translation._reserve_translation_usage("fixture", 7, "local-quota-user") is True
    assert translation._reserve_translation_usage("fixture", 4, "local-quota-user") is False


def test_redis_singleflight_uses_token_owned_lock(monkeypatch, tmp_path):
    class FakeRedis:
        values = {}
        calls = []

        def get(self, key):
            return self.values.get(key)

        def set(self, key, value, nx=False, ex=None):
            self.calls.append((key, value, nx, ex))
            if nx and key in self.values:
                return False
            self.values[key] = value
            return True

        def eval(self, *args):
            self.calls.append(args)
            return 1

    client = FakeRedis()
    monkeypatch.setattr(translation, "_redis", lambda: client)
    monkeypatch.setenv("TRANSLATION_CACHE_PATH", str(tmp_path / "flight-cache.sqlite3"))
    translated = {}
    owners, locks = translation._claim_distributed_flights(["flight fixture"], {"flight fixture": "key-1"}, translated)
    assert owners == ["flight fixture"] and "flight fixture" in locks
    key, token = locks["flight fixture"]
    assert key.endswith("key-1") and token
    translation._release_distributed_flights(locks)
    assert client.calls[-1][0] == translation._RELEASE_FLIGHT_LUA


def test_redis_translation_retry_queue_persists_owner_status(monkeypatch):
    class FakeRedis:
        values = {}
        queue = []

        def get(self, key):
            return self.values.get(key)

        def set(self, key, value, nx=False, ex=None):
            if nx and key in self.values:
                return False
            self.values[key] = value
            return True

        def rpush(self, _key, value):
            self.queue.append(value)

        def lpop(self, _key):
            return self.queue.pop(0) if self.queue else None

        def llen(self, _key):
            return len(self.queue)

    class ImmediateExecutor:
        def submit(self, function):
            function()

    client = FakeRedis()
    monkeypatch.setattr(translation, "_redis", lambda: client)
    monkeypatch.setattr(translation, "_RETRY_EXECUTOR", ImmediateExecutor())
    monkeypatch.setattr(translation.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(translation, "translate_paper_text", lambda *_args, **_kwargs: ("ترجمہ", "خلاصہ"))
    monkeypatch.setenv("TRANSLATION_BACKGROUND_RETRY_SECONDS", "0")
    job_id = translation.schedule_translation_retry("durable retry title 2026", "Abstract", "ur", user_id="durable-user", paper_id="paper-durable")
    assert job_id
    status = translation.get_translation_retry_status(job_id, "durable-user")
    assert status and status["status"] == "completed"
    assert status["translated_title"] == "ترجمہ" and status["paper_id"] == "paper-durable"
    assert translation.get_translation_retry_status(job_id, "other-user") is None


@pytest.fixture(autouse=True)
def isolate_translation_cache(tmp_path, monkeypatch):
    import app.services.ai_router as ai_router
    from app.services.ai_router.providers import AIResponse
    from app.services.ai_router.router import RouterUnavailable

    monkeypatch.setenv("TRANSLATION_CACHE_PATH", str(tmp_path / "translation-cache.sqlite3"))
    monkeypatch.setenv("RESORA_TESTING", "1")

    class FakeTranslationRouter:
        def complete(self, _task, prompt, *, validator=None, **_kwargs):
            payload = json.loads(prompt)
            for name in translation._provider_order(payload["target_language_code"]):
                provider = translation._PROVIDERS.get(name)
                if provider is None or not provider.supports(payload["source_language"], payload["target_language_code"]):
                    continue
                try:
                    values = provider.translate_batch(payload["segments"], payload["source_language"], payload["target_language_code"], payload.get("glossary"))
                    text = json.dumps(values, ensure_ascii=False)
                except Exception:
                    continue
                if validator is None or validator(text):
                    return AIResponse(name, "fake", text)
            raise RouterUnavailable("fake providers exhausted")

    monkeypatch.setattr(ai_router, "get_default_router", lambda: FakeTranslationRouter())
    clear_translation_cache()
    yield
    clear_translation_cache()


class StaticProvider:
    limits = translation.ProviderLimits(100, 100000, 24, 24000)

    def __init__(self, name, result):
        self.name, self.result, self.calls = name, result, 0

    def supports(self, source, target):
        return True

    def translate_batch(self, segments, source, target, glossary=None):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return [self.result(segment) if callable(self.result) else self.result for segment in segments]


def urdu_result(text):
    import re

    protected = re.findall(r"RESORATOKENX\d+XEND", text)
    return "یہ درست اردو ترجمہ ہے " + " ".join(protected)


def test_translation_preserves_doi_citation_math_and_numbers():
    clear_translation_cache()
    source = "Accuracy improved 86.9% [12]. DOI 10.1007/s12525-021-00475-2; equation x^2."
    provider = StaticProvider("fixture", urdu_result)
    with patch.dict(translation._PROVIDERS, {"fixture": provider}), patch.dict(os.environ, {"TRANSLATION_PROVIDER_ORDER": "fixture"}):
        translated = translate_text(source, "ur", source_language="en")
    for protected in ("86.9%", "[12]", "10.1007/s12525-021-00475-2", "x^2"):
        assert protected in translated


def test_local_argos_provider_posts_batch_and_preserves_target_codes(monkeypatch):
    import httpx

    provider = translation.ArgosLocalProvider()
    monkeypatch.setenv("LOCAL_TRANSLATOR_URL", "http://translator-local:8091")
    monkeypatch.setenv("LOCAL_TRANSLATION_LANGUAGES", "en,ur,ar,zh,es")
    translation._PROVIDER_HEALTH.pop("translator_local", None)
    monkeypatch.setattr(translation, "_rate_limit", lambda *_args: None)
    request = httpx.Request("POST", "http://translator-local:8091/translate")
    response = httpx.Response(200, json={"translations": ["Hola", "Mundo"]}, request=request)
    with patch("app.services.search.translation.httpx.post", return_value=response) as post:
        assert provider.supports("en", "es")
        assert not provider.supports("en", "fa")
        assert provider.translate_batch(["Hello", "World"], "en", "es") == ["Hola", "Mundo"]
        assert post.call_args.kwargs["json"]["target_language"] == "es"
        assert post.call_args.kwargs["json"]["segments"] == ["Hello", "World"]

def test_broken_protected_token_fails_over_to_next_provider():
    clear_translation_cache()
    first = StaticProvider("first", "missing markers")
    second = StaticProvider("second", urdu_result)
    with patch.dict(translation._PROVIDERS, {"first": first, "second": second}), patch.dict(os.environ, {"TRANSLATION_PROVIDER_ORDER": "first,second"}):
        translated = translate_text("See [4] at 10.1234/example", "ur", source_language="en")
    assert "[4]" in translated and "10.1234/example" in translated
    assert first.calls == 1 and second.calls == 1

def test_provider_failure_uses_next_provider():
    clear_translation_cache()
    first = StaticProvider("first", TranslationUnavailable("limited"))
    second = StaticProvider("second", urdu_result)
    with patch.dict(translation._PROVIDERS, {"first": first, "second": second}), patch.dict(os.environ, {"TRANSLATION_PROVIDER_ORDER": "first,second"}):
        assert translate_text("Hello", "ur", source_language="en").startswith("یہ درست")
    assert first.calls == 1 and second.calls == 1

def test_translation_cache_avoids_second_provider_call():
    clear_translation_cache()
    provider = StaticProvider("fixture", urdu_result)
    with patch.dict(translation._PROVIDERS, {"fixture": provider}), patch.dict(os.environ, {"TRANSLATION_PROVIDER_ORDER": "fixture"}):
        first = translation.translate_text("cache fixture", "ur", source_language="en", user_content=False)
        second = translation.translate_text("cache fixture", "ur", source_language="en", user_content=False)
    assert first == second and provider.calls == 1

def test_no_configured_provider_returns_safe_error():
    clear_translation_cache()
    with patch.dict(os.environ, {"TRANSLATION_PROVIDER_ORDER": "missing"}):
        with pytest.raises(TranslationUnavailable, match="temporarily unavailable"):
            translate_text("Pending translation", "ur", source_language="en")

def test_paper_language_filter_matches_detected_language():
    from app.schemas.paper import PaperRecord
    from app.services.search.discovery import apply_filters
    paper = PaperRecord(paper_id="u1", title="Urdu research", language="ur", source="fixture")
    matches = apply_filters([paper], min_citations=0, open_access_only=False, study_type=None, quartile=None, sample_size_min=None, paper_language="ur")
    assert matches == [paper]
    assert apply_filters([paper], min_citations=0, open_access_only=False, study_type=None, quartile=None, sample_size_min=None, paper_language="en") == []


def test_batch_deduplicates_identical_segments_before_provider_call():
    clear_translation_cache()
    provider = StaticProvider("fixture", urdu_result)
    with patch.dict(translation._PROVIDERS, {"fixture": provider}), patch.dict(os.environ, {"TRANSLATION_PROVIDER_ORDER": "fixture"}):
        results = translation.translate_batch(["same", "same", "different"], "ur", source_language="en", user_content=False)
    assert len(results) == 3
    assert results[0] == results[1]
    assert provider.calls == 1

def test_429_cooldown_is_recorded_and_fallback_is_immediate():
    clear_translation_cache()
    first = StaticProvider("limited", None)
    def throttled(_segments, _source, _target, _glossary=None):
        import httpx
        request = httpx.Request("POST", "https://provider.example")
        response = httpx.Response(429, headers={"Retry-After": "60"}, request=request)
        raise translation._provider_error("limited", httpx.HTTPStatusError("limited", request=request, response=response))
    first.translate_batch = throttled
    second = StaticProvider("fallback", urdu_result)
    with patch.dict(translation._PROVIDERS, {"limited": first, "fallback": second}), patch.dict(os.environ, {"TRANSLATION_PROVIDER_ORDER": "limited,fallback"}):
        result = translate_text("429 fixture", "ur", source_language="en")
        assert result.startswith("یہ درست")
        assert translation.translation_metrics()["limited"]["rate_limits"] == 1
        assert translation.translation_metrics()["limited"]["cooldown_seconds"] > 0
        assert second.calls == 1


def test_two_hundred_concurrent_identical_requests_coalesce_to_one_call():
    import time
    from concurrent.futures import ThreadPoolExecutor

    clear_translation_cache()
    class SlowProvider(StaticProvider):
        def translate_batch(self, segments, source, target, glossary=None):
            self.calls += 1
            time.sleep(0.04)
            return [urdu_result(segment) for segment in segments]
    provider = SlowProvider("load", None)
    with patch.dict(translation._PROVIDERS, {"load": provider}), patch.dict(os.environ, {"TRANSLATION_PROVIDER_ORDER": "load"}):
        with ThreadPoolExecutor(max_workers=40) as pool:
            results = list(pool.map(lambda _: translation.translate_text("shared load fixture", "ur", source_language="en", user_content=False), range(200)))
    assert len(results) == 200
    assert all(result == results[0] for result in results)
    assert provider.calls == 1


def test_requested_language_registry_extensions_and_scripts():
    requested = ("mr", "te", "gu", "kn", "ml", "pa-Guru", "fil", "ha", "am", "yo", "jv")
    assert all(language_profile(code).code == code for code in requested)
    assert canonical_language_code("pa-IN") == "pa-Guru"
    assert language_profile("pa-Guru").direction == "ltr"
    assert detect_language("\u0a2a\u0a70\u0a1c\u0a3e\u0a2c\u0a40 \u0a35\u0a3f\u0a71\u0a1a \u0a16\u0a4b\u0a1c")[0] == "pa-Guru"
