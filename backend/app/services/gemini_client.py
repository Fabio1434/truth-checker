"""Gemini adapter for Truth Checker.

Provides the same provider-compatible `messages.create(...)` surface as the
former Groq adapter, so the rest of the codebase (main.py, tests, etc.)
doesn't need to change. Internally it calls Google's Gemini API via the
`google-genai` SDK, using the built-in Google Search grounding tool for
web research. Unlike Groq, Gemini can read images natively in the same
call as the web-search request, so no separate vision pass is needed.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover - lets unit tests import without SDK
    genai = None  # type: ignore
    genai_types = None  # type: ignore


DEFAULT_MODEL = "gemini-2.5-flash"


class RateLimitError(Exception):
    """Raised when Gemini returns a 429 / RESOURCE_EXHAUSTED response."""


def _is_rate_limit(exc: Exception) -> bool:
    message = str(exc)
    return (
        "429" in message
        or "RESOURCE_EXHAUSTED" in message
        or "rate limit" in message.lower()
        or "quota" in message.lower()
    )


class GeminiMessages:
    def __init__(self, parent: "GeminiLLM") -> None:
        self.parent = parent

    def create(
        self,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        system: str | None = None,
        tools: list[dict] | None = None,
        messages: list[dict] | None = None,
    ) -> SimpleNamespace:
        model = model or self.parent.default_model
        messages = messages or []

        contents = self._convert_messages(messages)

        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if system:
            config_kwargs["system_instruction"] = system
        if tools:
            config_kwargs["tools"] = [genai_types.Tool(google_search=genai_types.GoogleSearch())]

        config = genai_types.GenerateContentConfig(**config_kwargs)

        try:
            response = self.parent.client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as e:  # normalize provider-specific errors
            if _is_rate_limit(e):
                raise RateLimitError(str(e)) from e
            raise

        return self.parent._normalize_response(response)

    @staticmethod
    def _convert_messages(messages: list[dict]) -> list:
        """Convert Anthropic-style messages (with optional image blocks) into
        Gemini `Content` objects. System prompt is handled separately via
        `system_instruction`, so only user/assistant turns land here."""
        contents = []
        for message in messages:
            role = message.get("role", "user")
            gemini_role = "model" if role == "assistant" else "user"
            content = message.get("content", "")
            parts = []
            if isinstance(content, str):
                parts.append(genai_types.Part.from_text(text=content))
            elif isinstance(content, list):
                for item in content:
                    item_type = item.get("type")
                    if item_type == "text":
                        parts.append(genai_types.Part.from_text(text=item.get("text", "")))
                    elif item_type == "image":
                        source = item.get("source", {})
                        data = source.get("data")
                        media_type = source.get("media_type", "image/jpeg")
                        if not data:
                            continue
                        import base64 as _b64

                        parts.append(
                            genai_types.Part.from_bytes(
                                data=_b64.b64decode(data),
                                mime_type=media_type,
                            )
                        )
            if parts:
                contents.append(genai_types.Content(role=gemini_role, parts=parts))
        return contents


class GeminiLLM:
    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.default_model = default_model or os.getenv("TRUTHCHECKER_MODEL", DEFAULT_MODEL)
        if not self.api_key or genai is None:
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key)
        self.messages = GeminiMessages(self)

    def _normalize_response(self, response: Any) -> SimpleNamespace:
        """Map a Gemini GenerateContentResponse onto the block-based shape
        the rest of the app expects (text blocks + server_tool_use blocks
        for search queries / visited sources)."""
        blocks: list[SimpleNamespace] = []

        text = (getattr(response, "text", None) or "").strip()
        if not text:
            # Fall back to concatenating text parts manually.
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                content = getattr(candidates[0], "content", None)
                parts = getattr(content, "parts", None) or []
                text = "".join(getattr(p, "text", "") or "" for p in parts).strip()
        blocks.append(SimpleNamespace(type="text", text=text))

        executed_tools: list[dict] = []
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            grounding_metadata = getattr(candidates[0], "grounding_metadata", None)
            if grounding_metadata:
                queries = getattr(grounding_metadata, "web_search_queries", None) or []
                for query in queries:
                    executed_tools.append({"name": "web_search", "query": query})
                    blocks.append(
                        SimpleNamespace(
                            type="server_tool_use",
                            name="web_search",
                            input={"query": query, "url": "", "search_results": []},
                        )
                    )

                chunks = getattr(grounding_metadata, "grounding_chunks", None) or []
                search_results = []
                for chunk in chunks:
                    web = getattr(chunk, "web", None)
                    if not web:
                        continue
                    uri = getattr(web, "uri", None)
                    title = getattr(web, "title", None)
                    if not uri:
                        continue
                    search_results.append({"url": uri, "title": title or ""})
                    executed_tools.append({"name": "web_fetch", "url": uri})
                    blocks.append(
                        SimpleNamespace(
                            type="server_tool_use",
                            name="web_fetch",
                            input={"query": "", "url": uri, "search_results": []},
                        )
                    )
                # Also attach the full result list to the first web_search block,
                # so downstream code building `verified_urls` sees every source
                # even if it only inspects search_results.
                if search_results:
                    for block in blocks:
                        if getattr(block, "type", None) == "server_tool_use" and block.name == "web_search":
                            block.input["search_results"] = search_results
                            break

        return SimpleNamespace(content=blocks, executed_tools=executed_tools)

    def close(self) -> None:
        # google-genai's client does not require explicit closing today,
        # but keep the method for interface parity with the old Groq client.
        self.client = None
