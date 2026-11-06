from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def deterministic_unconfigured_llm(monkeypatch):
    monkeypatch.setenv("RESORA_TESTING", "1")
    from app.services.models.adapters import AIRouterAdapter, ExtractiveAdapter, GroqAdapter, LLMOutput

    def fake_complete(self, prompt: str) -> LLMOutput:
        clean = " ".join(prompt.split())
        return LLMOutput(provider=self.provider_name, text=f"Deterministic test response: {clean[:220]}", confidence=0.42)

    monkeypatch.setattr(ExtractiveAdapter, "complete", fake_complete)
    monkeypatch.setattr(GroqAdapter, "complete", fake_complete)
    # Keep ordinary API tests isolated even when a developer has real keys in .env.
    monkeypatch.setattr(AIRouterAdapter, "complete", fake_complete)
