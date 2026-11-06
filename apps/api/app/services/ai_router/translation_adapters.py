"""Place existing official/local translation engines behind the AI router interface."""
from __future__ import annotations

import json
import os
import time

from .providers import AIResponse, ProviderFailure


class TranslationEngineAdapter:
    def __init__(self, name: str, engine, *, configured_env: tuple[str, ...], local: bool = False):
        self.name = name
        self.engine = engine
        self.configured_env = configured_env
        self.allow_user_content = local or os.getenv("AI_ROUTER_ALLOW_PRIVATE_TRANSLATION", "false").casefold() == "true"

    @property
    def available(self) -> bool:
        return any(os.getenv(key) for key in self.configured_env)

    def complete(self, model: str, messages: list[dict[str, str]], *, max_tokens: int = 1024) -> AIResponse:
        try:
            payload = json.loads(messages[-1]["content"])
            segments = payload["segments"]
            source = payload["source_language"]
            target = payload["target_language_code"]
            glossary = payload.get("glossary") or {}
            if not isinstance(segments, list) or not all(isinstance(item, str) for item in segments):
                raise ValueError("bad segments")
            if not self.engine.supports(source, target):
                raise ProviderFailure("translation route does not support this language pair")
            from app.services.search.translation import _rate_limit

            _rate_limit(self.engine, sum(map(len, segments)))
            started = time.monotonic()
            result = self.engine.translate_batch(segments, source, target, glossary)
            if len(result) != len(segments) or any(not isinstance(item, str) or not item.strip() for item in result):
                raise ProviderFailure("translation adapter returned an incomplete batch")
            return AIResponse(self.name, model, json.dumps(result, ensure_ascii=False), latency_ms=(time.monotonic() - started) * 1000)
        except ProviderFailure:
            raise
        except Exception as exc:
            # Never expose provider exception text; it can contain submitted text.
            raise ProviderFailure("translation provider failed") from exc

    def probe(self) -> None:
        if not self.engine.supports("en", "es"):
            raise ProviderFailure("probe language pair unavailable")
        from app.services.search.translation import _rate_limit

        _rate_limit(self.engine, len("OK"))
        self.engine.translate_batch(["OK"], "en", "es")


def translation_engine_providers() -> dict[str, TranslationEngineAdapter]:
    # Imported lazily because the translation coordinator also uses the router.
    from app.services.search.translation import (
        ArgosLocalProvider,
        AzureTranslatorProvider,
        DeepLProvider,
        MADLADSelfHostedProvider,
        OfficialGoogleCloudProvider,
    )

    return {
        "azure": TranslationEngineAdapter("azure", AzureTranslatorProvider(), configured_env=("AZURE_TRANSLATOR_KEY",)),
        "google_cloud": TranslationEngineAdapter("google_cloud", OfficialGoogleCloudProvider(), configured_env=("GOOGLE_TRANSLATE_PROJECT_ID",)),
        "deepl": TranslationEngineAdapter("deepl", DeepLProvider(), configured_env=("DEEPL_API_KEY",)),
        "madlad": TranslationEngineAdapter("madlad", MADLADSelfHostedProvider(), configured_env=("SELFHOSTED_TRANSLATOR_URL",), local=True),
        "translator_local": TranslationEngineAdapter("translator_local", ArgosLocalProvider(), configured_env=("LOCAL_TRANSLATOR_URL",), local=True),
    }
