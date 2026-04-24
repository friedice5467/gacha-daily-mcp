from src.tools.actions import ACTION_TOOLS
from src.tools.device import DEVICE_TOOLS
from src.tools.memory import MEMORY_TOOLS
from src.tools.perception import PERCEPTION_TOOLS

ALL_TOOLS = PERCEPTION_TOOLS + ACTION_TOOLS + DEVICE_TOOLS + MEMORY_TOOLS

TOOL_NAMES = [t["name"] for t in ALL_TOOLS]

__all__ = [
    "ACTION_TOOLS",
    "ALL_TOOLS",
    "DEVICE_TOOLS",
    "MEMORY_TOOLS",
    "PERCEPTION_TOOLS",
    "TOOL_NAMES",
]
