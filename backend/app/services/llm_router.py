"""Multi-provider LLM router for Truth Checker.

Tries Groq first (fast + generous free tier), then falls back to Gemini,
then to OpenAI, if a provider errors out or is rate-limited/out of quota.
Each adapter (groq_client / gemini_client / openai_client) exposes the same
`messages.create(...)` surface, so main.py doesn't need to know which
provider actually answered a given request — it just calls
`router.messages.create(...)` like it used to call a single client.

Only providers whose API key is configured are attempted. If none are
configured, `router.client` behaves like the old "no client" case (main.py
already checks `if not client:` before using it — see `is_configured`).
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

try:
    from app.services.groq_client import GroqLLM
except ImportError:  # pragma: no cover
    GroqLLM = None

try:
    from groq import RateLimitError as _GroqRateLimitError
except ImportError:  # pragma: no cover
    _GroqRateLimitError = None

try:
    from app.services.gemini_client import GeminiLLM, RateLimitError as _GeminiRateLimitError
except ImportError:  # pragma: no cover
    GeminiLLM = None
    _GeminiRateLimitError = None

try:
    from app.services.openai_client import OpenAILLM, RateLimitError as _OpenAIRateLimitError
except ImportError:  # pragma: no cover
    OpenAILLM = None
    _OpenAIRateLimitError = None


def _is_retryable_failure(exc: Exception) -> bool:
    """Whether this looks like a transient/quota/availability error worth
    falling back to the next provider for (as opposed to e.g. a bad request
    that would fail the same way on every provider)."""
    if _GroqRateLimitError is not None and isinstance(exc, _GroqRateLimitError):
        return True
    if _GeminiRateLimitError is not None and isinstance(exc, _GeminiRateLimitError):
        return True
    if _OpenAIRateLimitError is not None and isinstance(exc, _OpenAIRateLimitError):
        return True
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "429",
            "rate_limit",
            "rate limit",
            "resource_exhausted",
            "quota",
            "overloaded",
            "unavailable",
            "timeout",
            "timed out",
            "connection",
            "500",
            "502",
            "503",
        )
    )


class _RouterMessages:
    def __init__(self, router: "LLMRouter") -> None:
        self.router = router

    def create(self, **kwargs: Any) -> SimpleNamespace:
        last_exc: Exception | None = None
        for provider_name, provider_client, default_model in self.router.providers:
            call_kwargs = dict(kwargs)
            # Let each provider use its own default model unless the caller
            # explicitly asked for one that isn't the generic MODEL fallback.
            if not call_kwargs.get("model") or call_kwargs.get("model") == self.router.requested_model:
                call_kwargs["model"] = default_model
            try:
                response = provider_client.messages.create(**call_kwargs)
                response.provider = provider_name
                response.provider_model = call_kwargs["model"]
                return response
            except Exception as e:
                last_exc = e
                if _is_retryable_failure(e):
                    self.router.last_errors[provider_name] = str(e)
                    continue
                # Non-retryable error (e.g. bad request) — don't waste calls
                # on the other providers, they'd likely fail the same way.
                self.router.last_errors[provider_name] = str(e)
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError("Aucun provider LLM n'est configuré (GROQ_API_KEY / GEMINI_API_KEY / OPENAI_API_KEY).")


class LLMRouter:
    """Drop-in replacement for a single provider client. Configure providers
    via GROQ_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY — any subset works."""

    def __init__(self, requested_model: str | None = None) -> None:
        self.requested_model = requested_model
        self.last_errors: dict[str, str] = {}
        self.providers: list[tuple[str, Any, str]] = []

        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key and GroqLLM is not None:
            groq_client = GroqLLM(api_key=groq_key, default_model=os.getenv("TRUTHCHECKER_GROQ_MODEL", "groq/compound"))
            if groq_client.client is not None:
                self.providers.append(("groq", groq_client, groq_client.default_model))

        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key and GeminiLLM is not None:
            gemini_client = GeminiLLM(api_key=gemini_key, default_model=os.getenv("TRUTHCHECKER_GEMINI_MODEL", "gemini-2.5-flash"))
            if gemini_client.client is not None:
                self.providers.append(("gemini", gemini_client, gemini_client.default_model))

        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key and OpenAILLM is not None:
            openai_client = OpenAILLM(api_key=openai_key, default_model=os.getenv("TRUTHCHECKER_OPENAI_MODEL", "gpt-4.1"))
            if openai_client.client is not None:
                self.providers.append(("openai", openai_client, openai_client.default_model))

        self.messages = _RouterMessages(self)

    @property
    def is_configured(self) -> bool:
        return len(self.providers) > 0

    @property
    def configured_provider_names(self) -> list[str]:
        return [name for name, _, _ in self.providers]

    def close(self) -> None:
        for _, provider_client, _ in self.providers:
            try:
                provider_client.close()
            except Exception:
                pass
