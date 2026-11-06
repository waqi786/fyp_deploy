from dataclasses import dataclass


@dataclass
class LLMOutput:
    provider: str
    text: str
    confidence: float


class BaseLLMAdapter:
    provider_name = "base"

    def complete(self, prompt: str) -> LLMOutput:
        snippet = prompt.strip().replace("\n", " ")[:220]
        return LLMOutput(provider=self.provider_name, text=snippet, confidence=0.55)


class ExtractiveAdapter(BaseLLMAdapter):
    provider_name = "extractive"

    def complete(self, prompt: str) -> LLMOutput:
        raise RuntimeError("No external LLM is configured; using extractive backend analysis.")


class GroqAdapter(BaseLLMAdapter):
    provider_name = "groq"

    def complete(self, prompt: str) -> LLMOutput:
        return AIRouterAdapter().complete(prompt)


class AIRouterAdapter(BaseLLMAdapter):
    """All hosted LLM calls go through task-aware provider routing."""
    provider_name = "ai_router"

    def complete(self, prompt: str) -> LLMOutput:
        from app.services.ai_router import RouterUnavailable, get_default_router
        from app.services.ai_router.validators import numbers_are_grounded

        try:
            result = get_default_router().complete(
                "summary", prompt, user_content=True,
                validator=lambda output: numbers_are_grounded(output, prompt),
            )
        except RouterUnavailable:
            raise RuntimeError("AI service is temporarily unavailable; no eligible provider can safely process this content.") from None
        return LLMOutput(provider=result.provider, text=result.text, confidence=0.78)


class OpenAIAdapter(BaseLLMAdapter):
    provider_name = "openai"

    def complete(self, prompt: str) -> LLMOutput:
        return AIRouterAdapter().complete(prompt)


class ClaudeAdapter(BaseLLMAdapter):
    provider_name = "claude"

    def complete(self, prompt: str) -> LLMOutput:
        return AIRouterAdapter().complete(prompt)


class OllamaAdapter(BaseLLMAdapter):
    provider_name = "ollama"


class GeminiAdapter(BaseLLMAdapter):
    provider_name = "gemini"

    def complete(self, prompt: str) -> LLMOutput:
        return AIRouterAdapter().complete(prompt)


def build_llm_adapter(provider: str) -> BaseLLMAdapter:
    registry = {
        "extractive": ExtractiveAdapter,
        "groq": GroqAdapter,
        "openai": OpenAIAdapter,
        "claude": ClaudeAdapter,
        "ollama": OllamaAdapter,
        "gemini": GeminiAdapter,
        "ai_router": AIRouterAdapter,
    }
    return registry.get(provider.lower(), ExtractiveAdapter)()
