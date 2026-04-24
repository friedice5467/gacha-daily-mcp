from __future__ import annotations

import json
from typing import Any

import pytest

from src.engine.executor import ExecutionResult, execute_goal
from src.llm.base import LLMAdapter, LLMResponse, ToolCall
from src.safety.emergency import EmergencyStop, EmergencyStopError
from src.safety.guards import (
    BoundsError,
    CurrencyGuard,
    CurrencyGuardTriggered,
    UnknownScreenGuard,
    UnknownScreenGuardTriggered,
)
from src.safety.rate_limiter import RateLimiter
from src.tools import ACTION_TOOLS

SCENE = {
    "screen": "quest_select",
    "elements": [],
    "state": {"stamina_current": 47},
}


class DoneAdapter(LLMAdapter):
    def __init__(self):
        super().__init__(model="mock", max_tokens=1024)

    async def complete(self, messages, tools=None, image=None):
        return LLMResponse(text="DONE")


class SingleTapAdapter(LLMAdapter):
    def __init__(self):
        super().__init__(model="mock", max_tokens=1024)
        self._called = False

    async def complete(self, messages, tools=None, image=None):
        if not self._called:
            self._called = True
            return LLMResponse(
                text=None,
                tool_calls=[ToolCall(name="tap", arguments={"x": 0.5, "y": 0.8})],
            )
        return LLMResponse(text="DONE")


class OutOfBoundsTapAdapter(LLMAdapter):
    def __init__(self):
        super().__init__(model="mock", max_tokens=1024)

    async def complete(self, messages, tools=None, image=None):
        return LLMResponse(
            text=None,
            tool_calls=[ToolCall(name="tap", arguments={"x": 1.5, "y": 0.8})],
        )


class InfiniteAdapter(LLMAdapter):
    def __init__(self):
        super().__init__(model="mock", max_tokens=1024)

    async def complete(self, messages, tools=None, image=None):
        return LLMResponse(
            text=None,
            tool_calls=[ToolCall(name="wait", arguments={"seconds": 0.1})],
        )


async def _noop_handler(name: str, args: dict) -> dict:
    return {"status": "ok"}


def _make_deps(**overrides):
    defaults = {
        "rate_limiter": RateLimiter(max_per_minute=600),
        "emergency_stop": EmergencyStop(),
        "currency_guard": CurrencyGuard(),
        "unknown_guard": UnknownScreenGuard(enabled=False),
    }
    defaults.update(overrides)
    return defaults


async def test_immediate_done() -> None:
    deps = _make_deps()
    result = await execute_goal(
        goal="Do nothing",
        scene=SCENE,
        tools=ACTION_TOOLS,
        adapter=DoneAdapter(),
        tool_handler=_noop_handler,
        **deps,
    )
    assert result.success
    assert result.actions_taken == 0


async def test_single_tap_then_done() -> None:
    deps = _make_deps()
    result = await execute_goal(
        goal="Tap the start button",
        scene=SCENE,
        tools=ACTION_TOOLS,
        adapter=SingleTapAdapter(),
        tool_handler=_noop_handler,
        **deps,
    )
    assert result.success
    assert result.actions_taken == 1
    assert result.tool_calls[0].name == "tap"


async def test_bounds_check_rejects() -> None:
    deps = _make_deps()
    with pytest.raises(BoundsError):
        await execute_goal(
            goal="Tap off screen",
            scene=SCENE,
            tools=ACTION_TOOLS,
            adapter=OutOfBoundsTapAdapter(),
            tool_handler=_noop_handler,
            **deps,
        )


async def test_max_actions_limit() -> None:
    deps = _make_deps()
    result = await execute_goal(
        goal="Loop forever",
        scene=SCENE,
        tools=ACTION_TOOLS,
        adapter=InfiniteAdapter(),
        tool_handler=_noop_handler,
        max_actions=5,
        **deps,
    )
    assert not result.success
    assert result.actions_taken == 5
    assert "Max actions" in result.error


async def test_currency_guard_blocks() -> None:
    deps = _make_deps()
    scene_with_currency = {
        "screen": "shop",
        "state": {"premium_currency_dialog": True},
    }
    with pytest.raises(CurrencyGuardTriggered):
        await execute_goal(
            goal="Buy something",
            scene=scene_with_currency,
            tools=ACTION_TOOLS,
            adapter=DoneAdapter(),
            tool_handler=_noop_handler,
            **deps,
        )


async def test_unknown_screen_guard_blocks() -> None:
    deps = _make_deps(unknown_guard=UnknownScreenGuard(enabled=True))
    scene_unknown = {"screen": "unknown", "confidence": 0.1}
    with pytest.raises(UnknownScreenGuardTriggered):
        await execute_goal(
            goal="Do something",
            scene=scene_unknown,
            tools=ACTION_TOOLS,
            adapter=DoneAdapter(),
            tool_handler=_noop_handler,
            **deps,
        )


async def test_emergency_stop_halts() -> None:
    stop = EmergencyStop()
    stop.trigger()
    deps = _make_deps(emergency_stop=stop)
    with pytest.raises(EmergencyStopError):
        await execute_goal(
            goal="Do something",
            scene=SCENE,
            tools=ACTION_TOOLS,
            adapter=DoneAdapter(),
            tool_handler=_noop_handler,
            **deps,
        )
