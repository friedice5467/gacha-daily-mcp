from __future__ import annotations

import json
from typing import Any

import structlog
from pydantic import BaseModel, Field

from src.llm.base import LLMAdapter

log = structlog.get_logger()

BASE_SYSTEM_PROMPT = (
    "You are a game screen analyzer. Describe what you see. "
    "Report the screen type, visible UI elements with normalized positions, "
    "and state values. Respond only in JSON."
)


class UIElement(BaseModel):
    label: str
    type: str
    position: list[float]


class SceneState(BaseModel):
    screen: str = "unknown"
    elements: list[UIElement] = Field(default_factory=list)
    state: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    raw: str | None = None


class TaskStep(BaseModel):
    name: str
    vision_prompt: str
    conditions: list[dict[str, Any]]
    on_match: str | dict[str, Any]
    on_fail: str | dict[str, Any]
    max_retries: int = 5
    timeout_seconds: int = 60


async def analyze_screen(
    screenshot: bytes,
    step: TaskStep,
    adapter: LLMAdapter,
    game_context: str = "",
) -> SceneState:
    system_prompt = BASE_SYSTEM_PROMPT
    if game_context:
        system_prompt = f"{game_context}\n\n{system_prompt}"

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"Describe the current screen. Report whether you see: {step.vision_prompt}",
        },
    ]

    response = await adapter.complete(messages=messages, image=screenshot)

    if not response.text:
        log.warning("vision.empty_response", step=step.name)
        return SceneState(screen="unknown", confidence=0.0)

    return _parse_scene(response.text)


def _parse_scene(text: str) -> SceneState:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        log.warning("vision.parse_failed", text=text[:200])
        return SceneState(screen="unknown", confidence=0.0, raw=text)

    try:
        return SceneState(**data)
    except Exception:
        return SceneState(
            screen=data.get("screen", "unknown"),
            state=data.get("state", {}),
            confidence=data.get("confidence", 0.5),
            raw=text,
        )
