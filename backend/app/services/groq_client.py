"""Groq adapter for Truth Checker.

Provides a provider-compatible messages.create surface to minimize changes in the
existing services while using Groq's OpenAI-compatible Chat Completions API.
Text/URL fact checks use Groq Compound (web search + website visiting).
Image checks use Qwen 3.6 27B for vision, then Compound for web fact-checking.
"""

from __future__ import annotations

import base64
import os
from types import SimpleNamespace
from typing import Any

try:
    from groq import Groq
except ImportError:  # pragma: no cover - lets unit tests import without SDK
    Groq = None  # type: ignore


API_BASE_URL = "https://api.groq.com"
DEFAULT_MODEL = "groq/compound"
DEFAULT_VISION_MODEL = "qwen/qwen3.6-27b"
DEFAULT_HELPER_MODEL = "openai/gpt-oss-20b"


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class GroqMessages:
    def __init__(self, parent: "GroqLLM") -> None:
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
        is_json_task = bool(tools) or bool(system and "RÉPONSE JSON" in system)

        # Groq Compound is text-only. For image checks, first extract/interpret
        # the image with a vision model, then ask Compound to fact-check it.
        if self._contains_image(messages):
            return self._create_image_flow(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=messages,
            )

        groq_messages = self._convert_messages(messages, system)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": groq_messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
        if is_json_task:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.parent.client.chat.completions.create(**kwargs)
        return self.parent._normalize_response(response)

    def _create_image_flow(
        self,
        model: str,
        max_tokens: int,
        temperature: float,
        system: str | None,
        messages: list[dict],
    ) -> SimpleNamespace:
        vision_model = self.parent.vision_model
        vision_messages = self._convert_messages(messages, system, preserve_image=True)
        vision_prompt = (
            "Analyse cette image pour identifier le texte, les affirmations et les éléments "
            "factuels qu'elle présente. Décris précisément ce qui est lisible ou affirmé. "
            "N'invente aucun texte absent de l'image."
        )
        if vision_messages and vision_messages[-1]["role"] == "user":
            content = vision_messages[-1]["content"]
            if isinstance(content, list):
                content.insert(0, {"type": "text", "text": vision_prompt})
            else:
                vision_messages[-1]["content"] = f"{vision_prompt}\n{content}"

        vision_response = self.parent.client.chat.completions.create(
            model=vision_model,
            messages=vision_messages,
            temperature=0.1,
            max_completion_tokens=min(max_tokens, 2048),
        )
        image_text = (vision_response.choices[0].message.content or "").strip()
        if not image_text:
            raise RuntimeError("Le modèle vision n'a pas pu lire l'image.")

        fact_check_prompt = (
            (system or "")
            + "\n\nANALYSE D'IMAGE FOURNIE PAR LE MODÈLE VISION:\n"
            + image_text
            + "\n\nVérifie maintenant les affirmations identifiées dans l'image avec une recherche web "
              "réelle. Retourne uniquement le JSON demandé par le système."
        )
        fact_messages = [
            {"role": "system", "content": fact_check_prompt.strip()},
            {
                "role": "user",
                "content": (
                    "Cette demande provient d'une image. Analyse les affirmations visibles et "
                    "vérifie-les comme un fact-checker."
                ),
            },
        ]
        response = self.parent.client.chat.completions.create(
            model="groq/compound",
            messages=fact_messages,
            temperature=temperature,
            max_completion_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return self.parent._normalize_response(response, vision_text=image_text)

    @staticmethod
    def _contains_image(messages: list[dict]) -> bool:
        for message in messages:
            content = message.get("content")
            if isinstance(content, list):
                for item in content:
                    if item.get("type") in {"image", "image_url"}:
                        return True
        return False

    def _convert_messages(
        self,
        messages: list[dict],
        system: str | None,
        preserve_image: bool = False,
    ) -> list[dict]:
        converted: list[dict] = []
        if system:
            converted.append({"role": "system", "content": system})

        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if isinstance(content, list):
                parts: list[dict] = []
                for item in content:
                    if item.get("type") == "text":
                        parts.append({"type": "text", "text": item.get("text", "")})
                    elif item.get("type") == "image":
                        source = item.get("source", {})
                        data = source.get("data")
                        media_type = source.get("media_type", "image/jpeg")
                        if not data:
                            continue
                        # Groq accepts data URLs for base64 image input.
                        encoded_size = len(data) * 3 // 4
                        if encoded_size > 4 * 1024 * 1024:
                            raise ValueError("Image trop volumineuse pour l'API Groq (4 MB max en base64).")
                        parts.append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{media_type};base64,{data}"
                                },
                            }
                        )
                    elif item.get("type") == "image_url":
                        parts.append(item)
                content = parts
            converted.append({"role": role, "content": content})
        return converted


class GroqLLM:
    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
        vision_model: str | None = None,
        helper_model: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.default_model = default_model or os.getenv("TRUTHCHECKER_MODEL", DEFAULT_MODEL)
        self.vision_model = vision_model or os.getenv("TRUTHCHECKER_VISION_MODEL", DEFAULT_VISION_MODEL)
        self.helper_model = helper_model or os.getenv("TRUTHCHECKER_HELPER_MODEL", DEFAULT_HELPER_MODEL)
        if not self.api_key or Groq is None:
            self.client = None
        else:
            self.client = Groq(api_key=self.api_key, base_url=API_BASE_URL)
        self.messages = GroqMessages(self)

    def _normalize_response(self, response: Any, vision_text: str | None = None) -> SimpleNamespace:
        message = response.choices[0].message
        text = (getattr(message, "content", None) or "").strip()
        blocks: list[SimpleNamespace] = []

        if vision_text:
            blocks.append(SimpleNamespace(type="text", text=vision_text))

        blocks.append(SimpleNamespace(type="text", text=text))

        executed_tools = getattr(message, "executed_tools", None) or []
        for tool in executed_tools:
            tool_name = str(_get(tool, "name", ""))
            mapped_name = {
                "web_search": "web_search",
                "visit_website": "web_fetch",
                "web_fetch": "web_fetch",
            }.get(tool_name, tool_name)
            search_results = _get(tool, "search_results", []) or []
            query = _get(tool, "query", None) or _get(tool, "search_query", None) or ""
            visited_url = _get(tool, "url", None) or _get(tool, "website_url", None) or ""
            blocks.append(
                SimpleNamespace(
                    type="server_tool_use",
                    name=mapped_name,
                    input={
                        "query": query,
                        "url": visited_url,
                        "search_results": search_results,
                    },
                )
            )

        return SimpleNamespace(content=blocks, executed_tools=executed_tools)

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
