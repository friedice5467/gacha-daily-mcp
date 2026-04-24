from __future__ import annotations

from pydantic import BaseModel, Field


class LaunchAppInput(BaseModel):
    package: str = Field(description="Android package name (e.g. com.YoStarEN.Arknights)")


class CurrentAppInput(BaseModel):
    pass


class CurrentAppOutput(BaseModel):
    package: str | None


class ListPackagesInput(BaseModel):
    pass


class ListPackagesOutput(BaseModel):
    packages: list[str]


LAUNCH_APP_TOOL = {
    "name": "launch_app",
    "description": "Launch an app on the device by its package name.",
    "parameters": LaunchAppInput.model_json_schema(),
}

CURRENT_APP_TOOL = {
    "name": "current_app",
    "description": "Get the package name of the currently active app.",
    "parameters": CurrentAppInput.model_json_schema(),
}

LIST_PACKAGES_TOOL = {
    "name": "list_packages",
    "description": "List all third-party packages installed on the device.",
    "parameters": ListPackagesInput.model_json_schema(),
}

DEVICE_TOOLS = [LAUNCH_APP_TOOL, CURRENT_APP_TOOL, LIST_PACKAGES_TOOL]
