from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.llm.base import LLMAdapter, LLMResponse, TokenUsage, ToolCall
from src.llm.factory import get_adapter
from src.llm.tool_parser import parse_tool_calls_from_text
from src.server.database import Database, init_database


class MockVisionAdapter(LLMAdapter):
    def __init__(self, response_json: dict):
        super().__init__(model="mock-vision", max_tokens=1024)
        self._response_json = response_json

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        image: bytes | None = None,
    ) -> LLMResponse:
        return LLMResponse(
            text=json.dumps(self._response_json),
            tool_calls=[],
            usage=TokenUsage(input_tokens=100, output_tokens=50),
        )


async def test_mock_vision_returns_scene() -> None:
    scene = {
        "screen": "main_menu",
        "elements": [
            {"label": "Terminal", "type": "button", "position": [0.5, 0.8]},
        ],
        "state": {"stamina_current": 120, "stamina_max": 120},
    }
    adapter = MockVisionAdapter(scene)
    response = await adapter.complete(
        messages=[{"role": "user", "content": "Describe the screen"}],
        image=b"fake-png-data",
    )
    assert response.text is not None
    parsed = json.loads(response.text)
    assert parsed["screen"] == "main_menu"
    assert parsed["state"]["stamina_current"] == 120
    assert response.usage is not None
    assert response.usage.input_tokens == 100


async def test_mock_vision_no_image() -> None:
    adapter = MockVisionAdapter({"screen": "loading", "elements": [], "state": {}})
    response = await adapter.complete(
        messages=[{"role": "user", "content": "What do you see?"}],
    )
    parsed = json.loads(response.text)
    assert parsed["screen"] == "loading"


def test_tool_parser_json_block() -> None:
    text = """I'll tap the button.
```json
{"name": "tap", "arguments": {"x": 0.5, "y": 0.8}}
```
Done."""
    calls = parse_tool_calls_from_text(text, ["tap", "swipe"])
    assert len(calls) == 1
    assert calls[0].name == "tap"
    assert calls[0].arguments == {"x": 0.5, "y": 0.8}


def test_tool_parser_unknown_tool_ignored() -> None:
    text = '```json\n{"name": "delete_everything", "arguments": {}}\n```'
    calls = parse_tool_calls_from_text(text, ["tap", "swipe"])
    assert len(calls) == 0


def test_tool_parser_multiple_calls() -> None:
    text = """
```json
{"name": "tap", "arguments": {"x": 0.1, "y": 0.2}}
```
```json
{"name": "swipe", "arguments": {"sx": 0.1, "sy": 0.5, "ex": 0.9, "ey": 0.5}}
```
"""
    calls = parse_tool_calls_from_text(text, ["tap", "swipe"])
    assert len(calls) == 2
    assert calls[0].name == "tap"
    assert calls[1].name == "swipe"


def test_tool_parser_malformed_json() -> None:
    text = '```json\n{broken json\n```'
    calls = parse_tool_calls_from_text(text, ["tap"])
    assert len(calls) == 0


class CapturingAdapter(LLMAdapter):
    """Records messages sent to it so tests can inspect the system prompt."""

    def __init__(self, response_json: dict):
        super().__init__(model="mock", max_tokens=1024)
        self._response_json = response_json
        self.last_messages: list[dict] = []

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        image: bytes | None = None,
    ) -> LLMResponse:
        self.last_messages = messages
        return LLMResponse(text=json.dumps(self._response_json))


async def test_analyze_screen_parses_scene() -> None:
    from src.engine.vision import TaskStep, analyze_screen

    adapter = MockVisionAdapter({
        "screen": "quest_select",
        "elements": [{"label": "Start", "type": "button", "position": [0.5, 0.9]}],
        "state": {"stamina_current": 47, "stamina_max": 120},
    })
    step = TaskStep(
        name="Check quest",
        vision_prompt="Is there a quest available?",
        conditions=[],
        on_match="next",
        on_fail="retry",
    )
    scene = await analyze_screen(b"fake-png", step, adapter)
    assert scene.screen == "quest_select"
    assert scene.state["stamina_current"] == 47
    assert len(scene.elements) == 1


async def test_analyze_screen_with_game_context() -> None:
    from src.engine.vision import TaskStep, analyze_screen

    adapter = CapturingAdapter({"screen": "main_menu", "elements": [], "state": {}})
    step = TaskStep(
        name="Wait",
        vision_prompt="Is this the main menu?",
        conditions=[],
        on_match="next",
        on_fail="retry",
    )
    context = "This is Arknights, a tower defense gacha game. The main menu has a Terminal button."
    scene = await analyze_screen(b"fake-png", step, adapter, game_context=context)
    assert scene.screen == "main_menu"
    system_msg = adapter.last_messages[0]["content"]
    assert "Arknights" in system_msg
    assert "game screen analyzer" in system_msg


async def test_analyze_screen_no_game_context() -> None:
    from src.engine.vision import TaskStep, analyze_screen

    adapter = CapturingAdapter({"screen": "loading", "elements": [], "state": {}})
    step = TaskStep(
        name="Wait",
        vision_prompt="Is this loading?",
        conditions=[],
        on_match="next",
        on_fail="retry",
    )
    await analyze_screen(b"fake-png", step, adapter, game_context="")
    system_msg = adapter.last_messages[0]["content"]
    assert system_msg.startswith("You are a game screen analyzer")


async def test_analyze_screen_handles_bad_json() -> None:
    from src.engine.vision import TaskStep, analyze_screen

    class BadJsonAdapter(LLMAdapter):
        def __init__(self):
            super().__init__(model="mock", max_tokens=1024)

        async def complete(self, messages, tools=None, image=None):
            return LLMResponse(text="not valid json at all")

    step = TaskStep(
        name="Test",
        vision_prompt="anything",
        conditions=[],
        on_match="next",
        on_fail="retry",
    )
    scene = await analyze_screen(b"fake", step, BadJsonAdapter())
    assert scene.screen == "unknown"
    assert scene.confidence == 0.0
    assert scene.raw == "not valid json at all"


async def test_analyze_screen_handles_empty_response() -> None:
    from src.engine.vision import TaskStep, analyze_screen

    class EmptyAdapter(LLMAdapter):
        def __init__(self):
            super().__init__(model="mock", max_tokens=1024)

        async def complete(self, messages, tools=None, image=None):
            return LLMResponse(text=None)

    step = TaskStep(
        name="Test",
        vision_prompt="anything",
        conditions=[],
        on_match="next",
        on_fail="retry",
    )
    scene = await analyze_screen(b"fake", step, EmptyAdapter())
    assert scene.screen == "unknown"
    assert scene.confidence == 0.0


async def test_analyze_screen_strips_markdown_fence() -> None:
    from src.engine.vision import TaskStep, analyze_screen

    class FencedAdapter(LLMAdapter):
        def __init__(self):
            super().__init__(model="mock", max_tokens=1024)

        async def complete(self, messages, tools=None, image=None):
            return LLMResponse(text='```json\n{"screen": "battle", "elements": [], "state": {}}\n```')

    step = TaskStep(
        name="Test",
        vision_prompt="anything",
        conditions=[],
        on_match="next",
        on_fail="retry",
    )
    scene = await analyze_screen(b"fake", step, FencedAdapter())
    assert scene.screen == "battle"


async def test_factory_no_config_raises(tmp_path: Path) -> None:
    from src.llm.base import LLMNotConfiguredError
    from src.server import database as db_mod

    db = await init_database(tmp_path / "factory_test.db")
    original = db_mod._default_db
    try:
        with pytest.raises(LLMNotConfiguredError):
            await get_adapter("vision")
    finally:
        await db.close()
        db_mod._default_db = original


async def test_factory_returns_claude_adapter(tmp_path: Path) -> None:
    from src.llm.claude import ClaudeAdapter
    from src.server import database as db_mod

    db = await init_database(tmp_path / "factory_claude.db")
    original = db_mod._default_db
    try:
        async with db.get_db() as conn:
            await conn.execute(
                "INSERT INTO llm_config (id, role, backend, model, api_key) VALUES (?, ?, ?, ?, ?)",
                ("v1", "vision", "claude", "claude-sonnet-4-6", "sk-test-key"),
            )
            await conn.commit()
        adapter = await get_adapter("vision")
        assert isinstance(adapter, ClaudeAdapter)
        assert adapter.model == "claude-sonnet-4-6"
    finally:
        await db.close()
        db_mod._default_db = original


async def test_factory_returns_openai_compat_adapter(tmp_path: Path) -> None:
    from src.llm.openai_compat import OpenAICompatAdapter
    from src.server import database as db_mod

    db = await init_database(tmp_path / "factory_openai.db")
    original = db_mod._default_db
    try:
        async with db.get_db() as conn:
            await conn.execute(
                "INSERT INTO llm_config (id, role, backend, model, base_url) VALUES (?, ?, ?, ?, ?)",
                ("a1", "action", "openai_compat", "llama3", "http://localhost:1234/v1"),
            )
            await conn.commit()
        adapter = await get_adapter("action")
        assert isinstance(adapter, OpenAICompatAdapter)
        assert adapter.model == "llama3"
    finally:
        await db.close()
        db_mod._default_db = original
