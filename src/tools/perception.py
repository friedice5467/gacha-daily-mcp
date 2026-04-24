from __future__ import annotations

from pydantic import BaseModel, Field


class ScreenshotInput(BaseModel):
    pass


class ScreenshotOutput(BaseModel):
    image_base64: str
    width: int
    height: int


SCREENSHOT_TOOL = {
    "name": "screenshot",
    "description": "Take a screenshot of the current device screen. Returns a base64-encoded PNG image.",
    "parameters": ScreenshotInput.model_json_schema(),
}


class AnalyzeScreenInput(BaseModel):
    prompt: str = Field(description="What to look for on the screen")


class AnalyzeScreenOutput(BaseModel):
    screen: str
    elements: list[dict] = Field(default_factory=list)
    state: dict = Field(default_factory=dict)


ANALYZE_SCREEN_TOOL = {
    "name": "analyze_screen",
    "description": "Take a screenshot and analyze it with the vision LLM. Returns structured scene description.",
    "parameters": AnalyzeScreenInput.model_json_schema(),
}

PERCEPTION_TOOLS = [SCREENSHOT_TOOL, ANALYZE_SCREEN_TOOL]
