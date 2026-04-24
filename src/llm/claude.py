from __future__ import annotations

import base64
from typing import Any

import structlog
from anthropic import AsyncAnthropic

from src.llm.base import LLMAdapter, LLMError, LLMResponse, TokenUsage, ToolCall

log = structlog.get_logger()


class ClaudeAdapter(LLMAdapter):
    def __init__(self, model: str, api_key: str, max_tokens: int = 1024):
        super().__init__(model, max_tokens)
        self._client = AsyncAnthropic(api_key=api_key)

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

        system = _extract_system(messages)
        if system:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = _convert_tools(tools)

        try:
            response = await self._client.messages.create(**kwargs)
        except Exception as exc:
            raise LLMError(f"Claude API error: {exc}") from exc

        return _parse_response(response)


def _extract_system(messages: list[dict]) -> str | None:
    for msg in messages:
        if msg.get("role") == "system":
            return msg["content"]
    return None


def _build_messages(messages: list[dict], image: bytes | None) -> list[dict]:
    built = [m for m in messages if m.get("role") != "system"]

    if not image:
        return built

    if not built or built[-1]["role"] != "user":
        built.append({"role": "user", "content": ""})

    last = built[-1]
    text_content = last["content"] if isinstance(last["content"], str) else ""
    b64 = base64.standard_b64encode(image).decode("ascii")

    last["content"] = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
    ]
    if text_content:
        last["content"].append({"type": "text", "text": text_content})

    return built


def _convert_tools(tools: list[dict]) -> list[dict]:
    converted = []
    for t in tools:
        converted.append({
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("parameters", t.get("input_schema", {})),
        })
    return converted


def _parse_response(response: Any) -> LLMResponse:
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(ToolCall(name=block.name, arguments=block.input))

    usage = None
    if response.usage:
        usage = TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    return LLMResponse(
        text="\n".join(text_parts) if text_parts else None,
        tool_calls=tool_calls,
        usage=usage,
    )
