from __future__ import annotations

from pydantic import BaseModel, Field


class TapInput(BaseModel):
    x: float = Field(description="Normalized X coordinate (0.0–1.0)")
    y: float = Field(description="Normalized Y coordinate (0.0–1.0)")


class SwipeInput(BaseModel):
    start_x: float = Field(description="Start X (0.0–1.0)")
    start_y: float = Field(description="Start Y (0.0–1.0)")
    end_x: float = Field(description="End X (0.0–1.0)")
    end_y: float = Field(description="End Y (0.0–1.0)")
    duration_ms: int = Field(default=300, description="Swipe duration in milliseconds")


class WaitInput(BaseModel):
    seconds: float = Field(description="Seconds to wait", ge=0.1, le=30.0)


class KeyEventInput(BaseModel):
    keycode: int = Field(description="Android keycode to send (e.g. 4 = BACK, 3 = HOME)")


TAP_TOOL = {
    "name": "tap",
    "description": "Tap a point on the screen using normalized coordinates (0.0–1.0).",
    "parameters": TapInput.model_json_schema(),
}

SWIPE_TOOL = {
    "name": "swipe",
    "description": "Swipe from one point to another using normalized coordinates.",
    "parameters": SwipeInput.model_json_schema(),
}

WAIT_TOOL = {
    "name": "wait",
    "description": "Wait for a specified number of seconds before the next action.",
    "parameters": WaitInput.model_json_schema(),
}

KEY_EVENT_TOOL = {
    "name": "key_event",
    "description": "Send an Android key event (e.g. BACK=4, HOME=3, ENTER=66).",
    "parameters": KeyEventInput.model_json_schema(),
}

ACTION_TOOLS = [TAP_TOOL, SWIPE_TOOL, WAIT_TOOL, KEY_EVENT_TOOL]
