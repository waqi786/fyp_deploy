from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping

import httpx


class ProviderFailure(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


@dataclass(frozen=True)
class AIResponse:
    provider: str
    model: str
    text: str
    usage: int = 0
    headers: Mapping[str, str] = field(default_factory=dict)
    latency_ms: float = 0


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str = ""
    prompt_price: str | None = None
    completion_price: str | None = None
    context_length: int | None = None


class OpenAICompatibleProvider:
    """Small transport adapter for official OpenAI-compatible inference APIs."""

    def __init__(self, name: str, *, base_url: str, key_env: str, allow_user_content: bool,
                 timeout: float = 30, headers: Mapping[str, str] | None = None,
                 client: httpx.Client | None = None):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.key_env = key_env
        self.allow_user_content = allow_user_content
        self.timeout = timeout
        self.extra_headers = dict(headers or {})
        self._client = client

    @property
    def available(self) -> bool:
        return bool(os.getenv(self.key_env))

    def _headers(self) -> dict[str, str]:
        key = os.getenv(self.key_env, "")
        if not key:
            raise ProviderFailure("provider is not configured")
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json", **self.extra_headers}

    def list_models(self) -> list[ModelInfo]:
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.get(f"{self.base_url}/models", headers=self._headers())
            response.raise_for_status()
            return [ModelInfo(id=str(row.get("id", "")), name=str(row.get("name", "")))
                    for row in response.json().get("data", []) if row.get("id")]
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderFailure("model discovery failed", status_code=getattr(getattr(exc, "response", None), "status_code", None)) from exc
        finally:
            if self._client is None:
                client.close()

    @staticmethod
    def _failure(response: httpx.Response) -> ProviderFailure:
        retry_after = response.headers.get("retry-after")
        try:
            delay = float(retry_after) if retry_after else None
        except ValueError:
            delay = None
        # Never include a provider body here: it can echo submitted content.
        return ProviderFailure("provider request failed", status_code=response.status_code, retry_after=delay)

    def complete(self, model: str, messages: list[dict[str, str]], *, max_tokens: int = 1024,
                 temperature: float = 0) -> AIResponse:
        client = self._client or httpx.Client(timeout=self.timeout)
        started = time.monotonic()
        try:
            response = client.post(f"{self.base_url}/chat/completions", headers=self._headers(), json={
                "model": model, "messages": messages, "max_tokens": max_tokens,
                "temperature": temperature,
            })
            if response.is_error:
                raise self._failure(response)
            payload = response.json()
            text = str(payload["choices"][0]["message"]["content"])
            usage = int((payload.get("usage") or {}).get("total_tokens") or 0)
            return AIResponse(self.name, model, text, usage, dict(response.headers), (time.monotonic()-started)*1000)
        except ProviderFailure:
            raise
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            response = getattr(exc, "response", None)
            raise ProviderFailure("provider transport or response failure", status_code=getattr(response, "status_code", None)) from exc
        finally:
            if self._client is None:
                client.close()

    def stream(self, model: str, messages: list[dict[str, str]], *, max_tokens: int = 1024,
               temperature: float = 0) -> Iterator[str]:
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            with client.stream("POST", f"{self.base_url}/chat/completions", headers=self._headers(), json={
                "model": model, "messages": messages, "max_tokens": max_tokens,
                "temperature": temperature, "stream": True,
            }) as response:
                if response.is_error:
                    raise self._failure(response)
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = httpx.Response(200, text=data).json()["choices"][0]["delta"].get("content")
                    except (ValueError, KeyError, IndexError, TypeError):
                        continue
                    if delta:
                        yield str(delta)
        except ProviderFailure:
            raise
        except httpx.HTTPError as exc:
            raise ProviderFailure("provider stream failed", status_code=getattr(getattr(exc, "response", None), "status_code", None)) from exc
        finally:
            if self._client is None:
                client.close()


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter adapter with live model discovery and a strict free-model allowlist."""

    def __init__(self, **kwargs: Any):
        super().__init__("openrouter", base_url="https://openrouter.ai/api/v1", key_env="OPENROUTER_API_KEY",
                         allow_user_content=False, headers={"HTTP-Referer": "https://resora.app", "X-Title": "Resora"}, **kwargs)
        self._models_cache: tuple[float, list[ModelInfo]] = (0, [])

    @staticmethod
    def is_free_model(model_id: str) -> bool:
        return model_id.endswith(":free")

    def list_free_models(self, *, refresh: bool = False) -> list[ModelInfo]:
        cached_at, cached = self._models_cache
        if not refresh and time.monotonic() - cached_at < 900:
            return list(cached)
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.get(f"{self.base_url}/models", headers=self._headers())
            response.raise_for_status()
            models = []
            for row in response.json().get("data", []):
                model_id = str(row.get("id", ""))
                pricing = row.get("pricing") or {}
                if self.is_free_model(model_id) and pricing.get("prompt") == "0" and pricing.get("completion") == "0":
                    models.append(ModelInfo(model_id, str(row.get("name", "")), pricing.get("prompt"),
                                            pricing.get("completion"), row.get("context_length")))
            self._models_cache = (time.monotonic(), models)
            return list(models)
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise ProviderFailure("OpenRouter free-model discovery failed", status_code=getattr(getattr(exc, "response", None), "status_code", None)) from exc
        finally:
            if self._client is None:
                client.close()
