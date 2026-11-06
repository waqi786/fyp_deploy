from __future__ import annotations


import httpx
import pytest

from app.services.ai_router.providers import AIResponse, OpenRouterProvider, ProviderFailure
from app.services.ai_router.router import AIRouter, Route, RouterCache, RouterUnavailable


class FakeProvider:
    def __init__(self, name: str, *, allow_user_content: bool = True, response: str = "ok", error=None):
        self.name = name
        self.available = True
        self.allow_user_content = allow_user_content
        self.response = response
        self.error = error
        self.calls = []

    def complete(self, model, messages, *, max_tokens=1024):
        self.calls.append((model, messages, max_tokens))
        if self.error:
            raise self.error
        return AIResponse(self.name, model, self.response, usage=5, latency_ms=1)

    def stream(self, model, messages, *, max_tokens=1024):
        if self.error:
            raise self.error
        yield self.response[:2]
        yield self.response[2:]


def make_router(tmp_path, providers, routes, **kwargs):
    return AIRouter(providers, routes, cache=RouterCache(path=str(tmp_path / "cache.sqlite3")), **kwargs)


def test_weighted_round_robin_distributes_calls_across_healthy_providers(tmp_path):
    first, second = FakeProvider("first"), FakeProvider("second")
    router = make_router(tmp_path, {"first": first, "second": second}, {
        "summary": (Route("first", "m1", weight=2), Route("second", "m2", weight=1)),
    })
    outputs = [router.complete("summary", f"unique prompt {index}") for index in range(6)]
    assert len(outputs) == 6
    assert len(first.calls) == 4
    assert len(second.calls) == 2


def test_rate_limit_fails_over_same_request_without_exposing_provider_error(tmp_path):
    failure = FakeProvider("limited", error=ProviderFailure("429", status_code=429, retry_after=0))
    backup = FakeProvider("backup", response="recovered")
    router = make_router(tmp_path, {"limited": failure, "backup": backup}, {
        "chat": (Route("limited", "one"), Route("backup", "two")),
    }, failure_threshold=1)
    result = router.complete("chat", "same request", system="same system")
    assert result.text == "recovered"
    assert failure.calls[0][1] == backup.calls[0][1]
    assert router.metrics()["limited"]["rate_limits"] == 1


def test_stream_fails_over_before_first_chunk(tmp_path):
    blocked = FakeProvider("blocked", error=ProviderFailure("limited", status_code=429))
    backup = FakeProvider("backup", response="streamed")
    router = make_router(tmp_path, {"blocked": blocked, "backup": backup}, {
        "chat": (Route("blocked", "a"), Route("backup", "b")),
    }, failure_threshold=1)
    assert "".join(router.stream("chat", "prompt")) == "streamed"


def test_provider_at_ninety_percent_daily_budget_is_skipped(tmp_path):
    exhausted = FakeProvider("exhausted")
    healthy = FakeProvider("healthy")
    router = make_router(tmp_path, {"exhausted": exhausted, "healthy": healthy}, {
        "summary": (Route("exhausted", "a", daily_request_limit=10), Route("healthy", "b")),
    }, daily_usage={"exhausted": 9})
    assert router.complete("summary", "budget routing").provider == "healthy"
    assert exhausted.calls == []


def test_shared_redis_quota_reservation_skips_limited_provider(tmp_path):
    class BudgetRedis:
        def __init__(self):
            self.keys = []

        def eval(self, _script, key_count, *args):
            self.keys = list(args[:key_count])
            return 0 if ":blocked:" in self.keys[0] else 1

    redis = BudgetRedis()
    blocked, backup = FakeProvider("blocked"), FakeProvider("backup")
    router = make_router(tmp_path, {"blocked": blocked, "backup": backup}, {
        "summary": (Route("blocked", "a"), Route("backup", "b")),
    }, redis_client=redis, provider_limits={"blocked": {"rpm": 10, "tpm": 1000, "rpd": 100, "tpd": 10000}})
    assert router.complete("summary", "safe fixture").provider == "backup"
    assert blocked.calls == []
    assert len(redis.keys) == 6
    assert all("safe fixture" not in key for key in redis.keys)
    assert router.metrics()["blocked"]["budget_blocks"] == 1


def test_circuit_breaker_cools_provider_then_allows_retry(tmp_path):
    now = [100.0]
    primary = FakeProvider("primary", error=ProviderFailure("down", status_code=503, retry_after=3))
    router = make_router(tmp_path, {"primary": primary}, {"summary": (Route("primary", "a"),)},
                         failure_threshold=1, clock=lambda: now[0])
    with pytest.raises(RouterUnavailable):
        router.complete("summary", "first failure")
    assert router.provider_health()["primary"]["healthy"] is False
    with pytest.raises(RouterUnavailable):
        router.complete("summary", "during cooldown")
    now[0] += 4
    primary.error = None
    assert router.complete("summary", "after cooldown").provider == "primary"


def test_cache_hit_avoids_second_provider_call(tmp_path):
    provider = FakeProvider("cached")
    router = make_router(tmp_path, {"cached": provider}, {"summary": (Route("cached", "model"),)})
    first = router.complete("summary", "same result")
    second = router.complete("summary", " same   result ")
    assert first.text == second.text
    assert len(provider.calls) == 1
    assert router.metrics()["cached"]["cache_hits"] == 1


def test_user_content_is_never_persisted_in_response_cache(tmp_path):
    private = FakeProvider("private")
    router = make_router(tmp_path, {"private": private}, {"chat": (Route("private", "model"),)})
    router.complete("chat", "private notes", user_content=True)
    assert router.cache.get(router._cache_key("chat", "private notes", "private", "v1")) is None
    router.complete("chat", "private notes", user_content=True)
    assert len(private.calls) == 2


def test_rate_limit_response_headers_are_reduced_to_numeric_metrics(tmp_path):
    class HeaderProvider(FakeProvider):
        def complete(self, model, messages, *, max_tokens=1024):
            self.calls.append((model, messages, max_tokens))
            return AIResponse(self.name, model, "ok", usage=5,
                              headers={"x-ratelimit-remaining-requests": "12", "authorization": "secret"})

    provider = HeaderProvider("headers")
    router = make_router(tmp_path, {"headers": provider}, {"summary": (Route("headers", "model"),)})
    router.complete("summary", "rate telemetry")
    assert router.metrics()["headers"]["requests_remaining"] == 12
    assert "authorization" not in router.metrics()["headers"]


def test_hosted_translation_adapter_uses_router_and_marks_input_private(monkeypatch):
    from app.services.search import translation

    captured = {}

    class TranslationRouter:
        def complete(self, task, prompt, **kwargs):
            captured.update(task=task, prompt=prompt, kwargs=kwargs)
            return AIResponse("groq", "fake-model", '["traduction"]')

    monkeypatch.setattr("app.services.ai_router.get_default_router", lambda: TranslationRouter())
    assert translation.GroqTranslationProvider().translate_batch(["research"], "en", "fr") == ["traduction"]
    assert captured["task"] == "short_translation"
    assert captured["kwargs"]["user_content"] is True
    assert captured["kwargs"]["validator"]('["valid"]') is True
    assert captured["kwargs"]["validator"]("not-json") is False


def test_invalid_output_retries_on_different_provider(tmp_path):
    invalid, valid = FakeProvider("invalid", response="not-json"), FakeProvider("valid", response='{"ok": true}')
    router = make_router(tmp_path, {"invalid": invalid, "valid": valid}, {
        "extraction": (Route("invalid", "a"), Route("valid", "b")),
    })
    response = router.complete("extraction", "extract fields", validator=lambda text: text.startswith("{"))
    assert response.provider == "valid"
    assert router.metrics()["invalid"]["validation_failures"] == 1


def test_user_content_is_blocked_from_provider_without_acceptable_terms(tmp_path):
    no_user_content = FakeProvider("public_only", allow_user_content=False)
    private_ok = FakeProvider("private_ok", allow_user_content=True)
    router = make_router(tmp_path, {"public_only": no_user_content, "private_ok": private_ok}, {
        "chat": (Route("public_only", "a"), Route("private_ok", "b")),
    })
    assert router.complete("chat", "private notes", user_content=True).provider == "private_ok"
    assert no_user_content.calls == []


def test_openrouter_paid_model_is_blocked_when_free_only_is_enabled(tmp_path):
    provider = FakeProvider("openrouter")
    router = make_router(tmp_path, {"openrouter": provider}, {
        "summary": (Route("openrouter", "vendor/model"),),
    }, free_models_only=True)
    with pytest.raises(RouterUnavailable):
        router.complete("summary", "must not use paid model")
    assert provider.calls == []
    assert router.metrics()["openrouter"]["paid_model_blocks"] == 1


def test_openrouter_model_discovery_accepts_only_explicit_free_ids_and_zero_prices(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    payload = {"data": [
        {"id": "vendor/free-model:free", "name": "Free", "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "vendor/paid-model", "name": "Paid", "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "vendor/odd-free:free", "name": "Priced", "pricing": {"prompt": "0.1", "completion": "0"}},
    ]}
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))
    provider = OpenRouterProvider(client=client)
    assert [model.id for model in provider.list_free_models(refresh=True)] == ["vendor/free-model:free"]


def test_dynamic_qwen_pool_uses_only_free_qwen_models(monkeypatch, tmp_path):
    from app.services.ai_router.providers import ModelInfo

    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    provider = OpenRouterProvider(client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": []}))))
    provider.list_free_models = lambda **_kwargs: [
        ModelInfo("qwen/qwen3-8b:free", "Qwen", "0", "0", 32000),
        ModelInfo("qwen/qwen3-32b:free", "Qwen Large", "0", "0", 64000),
        ModelInfo("other/model:free", "Other", "0", "0", 96000),
    ]
    router = make_router(tmp_path, {"openrouter": provider}, {
        "ui_translation": (Route("openrouter", "auto-qwen-free"),),
        "judge": (Route("openrouter", "auto-qwen-free-judge"),),
    })
    assert [route.model for route in router._expanded("ui_translation")] == ["qwen/qwen3-8b:free"]
    assert [route.model for route in router._expanded("judge")] == ["qwen/qwen3-32b:free"]


def test_language_specific_weights_promote_qwen_for_asian_languages(tmp_path):
    qwen, gemini = FakeProvider("openrouter"), FakeProvider("gemini")
    router = make_router(tmp_path, {"openrouter": qwen, "gemini": gemini}, {
        "short_translation": (
            Route("gemini", "g", weight=1),
            Route("openrouter", "qwen:free", weight=1, language_weight=4, languages=("zh-Hans", "ja")),
        ),
    })
    chinese = [router._ordered("short_translation", list(router._candidates("short_translation", user_content=False, prompt_length=1)), "zh-Hans")[0].provider for _ in range(20)]
    spanish = [router._ordered("short_translation", list(router._candidates("short_translation", user_content=False, prompt_length=1)), "es")[0].provider for _ in range(20)]
    assert chinese.count("openrouter") > spanish.count("openrouter")


def test_provider_health_probe_is_tiny_and_reports_daily_quota(tmp_path):
    provider = FakeProvider("probe")
    class Redis:
        def eval(self, *_args):
            return 1

        def setex(self, *_args):
            return True

    router = make_router(tmp_path, {"probe": provider}, {"summary": (Route("probe", "model"),)},
                         provider_limits={"probe": {"rpd": 20}}, redis_client=Redis())
    result = router.probe_provider("probe")
    assert result["healthy"] is True
    assert provider.calls[0][2] == 1
    status = router.provider_health()["probe"]
    assert status["daily_quota"] == {"limit": 20, "used": 1, "remaining": 19}


def test_task_output_validators_check_placeholders_scripts_evidence_numbers_and_judgment():
    from app.services.ai_router.validators import (
        extraction_json_is_valid,
        judge_json_is_valid,
        numbers_are_grounded,
        translation_output_is_valid,
    )

    assert translation_output_is_valid("Hello {name}", "नमस्ते {name}", "hi")
    assert not translation_output_is_valid("Hello {name}", "नमस्ते", "hi")
    assert not translation_output_is_valid("Hello", "Hello", "ur")
    assert extraction_json_is_valid('{"method":"study","evidence":["We enrolled 18 participants."]}', "We enrolled 18 participants.")
    assert not extraction_json_is_valid('{"evidence":["We enrolled 81 people."]}', "We enrolled 18 participants.")
    assert numbers_are_grounded("The sample had 18 participants (12%).", "sample: 18 participants, 12%") is True
    assert not numbers_are_grounded("It had 13 participants.", "sample: 18 participants")
    assert judge_json_is_valid('{"choice":"merge","merged_text":"Combined","reason":"Both contain evidence"}')
    assert not judge_json_is_valid('{"choice":"maybe","reason":"unclear"}')


def test_direct_hosted_llm_sdk_imports_are_restricted_to_router():
    from pathlib import Path

    services = Path(__file__).resolve().parents[1] / "services"
    forbidden = ("from openai import", "import openai", "from groq import", "import groq",
                 "import google.generativeai", "from google import genai")
    violations = []
    for path in services.rglob("*.py"):
        if "ai_router" in path.parts or "tests" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        if any(token in source for token in forbidden):
            violations.append(str(path.relative_to(services)))
    assert not violations, f"Hosted LLM SDK calls must be made by ai_router: {violations}"


def test_translation_engine_adapter_runs_existing_engine_inside_router(monkeypatch):
    from app.services.ai_router.translation_adapters import TranslationEngineAdapter

    class FakeTranslationEngine:
        name = "fake_translate"
        limits = type("Limits", (), {"requests_per_second": 10, "characters_per_minute": 10000,
                                      "max_batch_size": 20, "max_chars_per_batch": 10000})()

        def supports(self, source, target):
            return source == "en" and target == "ur"

        def translate_batch(self, segments, source, target, glossary=None):
            return ["ترجمہ " + text for text in segments]

    monkeypatch.setenv("FAKE_TRANSLATION_TOKEN", "configured")
    adapter = TranslationEngineAdapter("fake_translate", FakeTranslationEngine(), configured_env=("FAKE_TRANSLATION_TOKEN",), local=True)
    result = adapter.complete("translate", [{"role": "user", "content": '{"segments":["Hello"],"source_language":"en","target_language_code":"ur"}'}])
    assert result.provider == "fake_translate"
    assert result.text == '["ترجمہ Hello"]'


def test_private_translation_bypasses_translation_result_cache(monkeypatch, tmp_path):
    from app.services.search import translation

    provider = FakeProvider("groq", allow_user_content=True, response='["ترجمہ"]')
    router = make_router(tmp_path, {"groq": provider}, {"short_translation": (Route("groq", "model"),)})
    monkeypatch.setattr("app.services.ai_router.get_default_router", lambda: router)
    first = translation.translate_batch(["private text"], "ur", source_language="en", user_content=True)
    second = translation.translate_batch(["private text"], "ur", source_language="en", user_content=True)
    assert first == second == ["ترجمہ"]
    assert len(provider.calls) == 2

