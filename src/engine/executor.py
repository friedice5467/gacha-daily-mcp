from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import structlog

from src.llm.base import LLMAdapter, LLMResponse, ToolCall
from src.safety.emergency import EmergencyStop
from src.safety.guards import BoundsChecker, CurrencyGuard, UnknownScreenGuard
from src.safety.rate_limiter import RateLimiter

log = structlog.get_logger()

ACTION_SYSTEM_PROMPT = (
    "You are a game automation agent. You have access to tools for interacting with a mobile device. "
    "Execute the minimum actions needed to achieve the goal, then respond with DONE."
)


class ExecutorError(Exception):
    pass


@dataclass
class ExecutionResult:
    success: bool
    actions_taken: int = 0
    tool_calls: list[ToolCall] = field(default_factory=list)
    error: str | None = None


async def execute_goal(
    goal: str,
    scene: dict[str, Any],
    tools: list[dict],
    adapter: LLMAdapter,
    tool_handler: Any,
    rate_limiter: RateLimiter,
    emergency_stop: EmergencyStop,
    currency_guard: CurrencyGuard,
    unknown_guard: UnknownScreenGuard,
    max_actions: int = 50,
) -> ExecutionResult:
    currency_guard.check(scene)
    unknown_guard.check(scene)

    tool_names_str = ", ".join(t["name"] for t in tools)
    scene_summary = json.dumps(scene, default=str)

    messages: list[dict] = [
        {"role": "system", "content": ACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Available tools: {tool_names_str}\n"
                f"Current screen: {scene_summary}\n"
                f"Goal: {goal}\n"
                "Execute minimum actions. Respond DONE when finished."
            ),
        },
    ]

    all_calls: list[ToolCall] = []
    actions = 0

    for _ in range(max_actions):
        await emergency_stop.check()
        await rate_limiter.acquire()

        response = await adapter.complete(messages=messages, tools=tools)

        if _is_done(response):
            return ExecutionResult(success=True, actions_taken=actions, tool_calls=all_calls)

        if not response.tool_calls:
            return ExecutionResult(success=True, actions_taken=actions, tool_calls=all_calls)

        for tc in response.tool_calls:
            await emergency_stop.check()
            BoundsChecker.check_tool_call(tc.name, tc.arguments)
            await rate_limiter.acquire()

            result = await tool_handler(tc.name, tc.arguments)
            all_calls.append(tc)
            actions += 1

            messages.append({
                "role": "assistant",
                "content": f"Called {tc.name}({json.dumps(tc.arguments)})",
            })
            messages.append({
                "role": "user",
                "content": f"Result: {json.dumps(result, default=str)}",
            })

            log.debug("executor.tool_call", tool=tc.name, args=tc.arguments, actions=actions)

    return ExecutionResult(
        success=False,
        actions_taken=actions,
        tool_calls=all_calls,
        error=f"Max actions ({max_actions}) reached",
    )


def _is_done(response: LLMResponse) -> bool:
    if response.text and "DONE" in response.text.upper():
        return True
    return False
