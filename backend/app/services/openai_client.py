"""OpenAI adapter for Truth Checker.

Same provider-compatible `messages.create(...)` surface as the Groq/Gemini
adapters. Uses OpenAI's Responses API with the built-in `web_search_preview`
tool for research, and native multimodal input for image fact-checks.
"""

from __future__ import annotations

import base64
import os
from types import SimpleNamespace
from typing import Any

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - lets unit tests import without SDK
    OpenAI = None  # type: ignore


DEFAULT_MODEL = "gpt-4.1"


class RateLimitError(Exception):
    """Raised when OpenAI returns a 429 / quota-exceeded response."""


def _is_rate_limit(exc: Exception) -> bool:
    message = str(exc)
    return (
        "429" in message
        or "rate_limit" in message.lower()
        or "insufficient_quota" in message.lower()
        or "quota" in message.lower()
    )


class OpenAIMessages:
    def __init__(self, parent: "OpenAILLM") -> None:
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

        input_items = self._convert_messages(messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "input": input_items,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if system:
            kwargs["instructions"] = system
        if tools:
            kwargs["tools"] = [{"type": "web_search_preview"}]
            kwargs["include"] = ["web_search_call.action.sources"]

        try:
            response = self.parent.client.responses.create(**kwargs)
        except Exception as e:
            if _is_rate_limit(e):
                raise RateLimitError(str(e)) from e
            raise

        return self.parent._normalize_response(response)

    @staticmethod
    def _convert_messages(messages: list[dict]) -> list[dict]:
        """Convert Anthropic-style messages (with optional image blocks) into
        Responses API `input` items."""
        input_items: list[dict] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if isinstance(content, str):
                input_items.append({"role": role, "content": content})
                continue

            parts: list[dict] = []
            for item in content:
                item_type = item.get("type")
                if item_type == "text":
                    parts.append({"type": "input_text", "text": item.get("text", "")})
                elif item_type == "image":
                    source = item.get("source", {})
                    data = source.get("data")
                    media_type = source.get("media_type", "image/jpeg")
                    if not data:
                        continue
                    parts.append(
                        {
                            "type": "input_image",
                            "image_url": f"data:{media_type};base64,{data}",
                        }
                    )
            input_items.append({"role": role, "content": parts})
        return input_items


class OpenAILLM:
    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.default_model = default_model or os.getenv("TRUTHCHECKER_OPENAI_MODEL", DEFAULT_MODEL)
        if not self.api_key or OpenAI is None:
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key)
        self.messages = OpenAIMessages(self)

    def _normalize_response(self, response: Any) -> SimpleNamespace:
        blocks: list[SimpleNamespace] = []
        executed_tools: list[dict] = []

        output_items = getattr(response, "output", None) or []
        for item in output_items:
            item_type = getattr(item, "type", None)

            if item_type == "message":
                for content_part in getattr(item, "content", None) or []:
                    part_type = getattr(content_part, "type", None)
                    if part_type in ("output_text", "text"):
                        text = getattr(content_part, "text", "") or ""
                        if text:
                            blocks.append(SimpleNamespace(type="text", text=text))

            elif item_type == "web_search_call":
                action = getattr(item, "action", None)
                query = getattr(action, "query", None) or ""
                executed_tools.append({"name": "web_search", "query": query})
                search_results = []
                for source in getattr(action, "sources", None) or []:
                    url = getattr(source, "url", None) or (
                        source.get("url") if isinstance(source, dict) else None
                    )
                    title = getattr(source, "title", None) or (
                        source.get("title") if isinstance(source, dict) else ""
                    )
                    if url:
                        search_results.append({"url": url, "title": title or ""})
                blocks.append(
                    SimpleNamespace(
                        type="server_tool_use",
                        name="web_search",
                        input={"query": query, "url": "", "search_results": search_results},
                    )
                )
                for result in search_results:
                    blocks.append(
                        SimpleNamespace(
                            type="server_tool_use",
                            name="web_fetch",
                            input={"query": "", "url": result["url"], "search_results": []},
                        )
                    )

        if not blocks:
            fallback_text = (getattr(response, "output_text", None) or "").strip()
            blocks.append(SimpleNamespace(type="text", text=fallback_text))

        return SimpleNamespace(content=blocks, executed_tools=executed_tools)

    def close(self) -> None:
        self.client = None
