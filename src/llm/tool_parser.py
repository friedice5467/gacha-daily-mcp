from __future__ import annotations

import json
import re

from src.llm.base import ToolCall


def parse_tool_calls_from_text(text: str, available_tools: list[str]) -> list[ToolCall]:
    """Fallback parser for models that embed tool calls in text instead of using native tool calling."""
    calls: list[ToolCall] = []

    json_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not json_blocks:
        json_blocks = re.findall(r"(\{[^{}]*\"name\"[^{}]*\"arguments\"[^{}]*\})", text, re.DOTALL)

    for block in json_blocks:
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError:
            continue

        name = parsed.get("name") or parsed.get("function") or parsed.get("tool")
        args = parsed.get("arguments") or parsed.get("params") or parsed.get("input") or {}

        if not name or name not in available_tools:
            continue

        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                continue

        calls.append(ToolCall(name=name, arguments=args))

    return calls
