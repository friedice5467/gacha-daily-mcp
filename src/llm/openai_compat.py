from __future__ import annotations

import base64
import json
from typing import Any

import structlog
from openai import AsyncOpenAI

from src.llm.base import LLMAdapter, LLMError, LLMResponse, TokenUsage, ToolCall

log = structlog.get_logger()


class OpenAICompatAdapter(LLMAdapter):
    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str = "not-needed",
        max_tokens: int = 1024,
        tool_calling_mode: str = "native",
    ):
        super().__init__(model, max_tokens)
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._tool_calling_mode = tool_calling_mode

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        image: bytes | None = None,
    ) -> LLMResponse:
        built_messages = _build_messages(messages, image)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": built_messages,
        }

        if tools and self._tool_calling_mode == "native":
            kwargs["tools"] = _convert_tools(tools)

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise LLMError(f"OpenAI-compat API error: {exc}") from exc

        return _parse_response(response)


def _build_messages(messages: list[dict], image: bytes | None) -> list[dict]:
    built = []
    for msg in messages:
        built.append({"role": msg["role"], "content": msg["content"]})

    if not image:
        return built

    if not built or built[-1]["role"] != "user":
        built.append({"role": "user", "content": ""})

    last = built[-1]
    text_content = last["content"] if isinstance(last["content"], str) else ""
    b64 = base64.standard_b64encode(image).decode("ascii")

    content_parts: list[dict] = [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
    ]
    if text_content:
        content_parts.append({"type": "text", "text": text_content})

    last["content"] = content_parts
    return built


def _convert_tools(tools: list[dict]) -> list[dict]:
    converted = []
    for t in tools:
        converted.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("parameters", t.get("input_schema", {})),
            },
        })
    return converted


def _parse_response(response: Any) -> LLMResponse:
    choice = response.choices[0]
    message = choice.message

    text = message.content
    tool_calls: list[ToolCall] = []

    if message.tool_calls:
        for tc in message.tool_calls:
            args = tc.function.arguments
            if isinstance(args, str):
                args = json.loads(args)
            tool_calls.append(ToolCall(name=tc.function.name, arguments=args))

    usage = None
    if response.usage:
        usage = TokenUsage(
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )

    return LLMResponse(text=text, tool_calls=tool_calls, usage=usage)
