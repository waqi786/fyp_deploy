"""Task-aware, privacy-aware multi-provider inference routing."""

from .router import (
    AIResponse,
    AIRouter,
    ProviderFailure,
    RouterUnavailable,
    get_default_router,
)

__all__ = ["AIRouter", "AIResponse", "ProviderFailure", "RouterUnavailable", "get_default_router"]
