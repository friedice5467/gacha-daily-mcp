from __future__ import annotations

import asyncio
from typing import Any

import structlog

log = structlog.get_logger()


class GuardError(Exception):
    pass


class CurrencyGuardTriggered(GuardError):
    pass


class UnknownScreenGuardTriggered(GuardError):
    pass


class BoundsError(GuardError):
    pass


class CurrencyGuard:
    def __init__(self, enabled: bool = True):
        self._enabled = enabled
        self._confirmed = asyncio.Event()

    def check(self, scene: dict[str, Any]) -> None:
        if not self._enabled:
            return
        state = scene.get("state", {})
        if state.get("premium_currency_dialog") or state.get("purchase_prompt"):
            log.warning("guard.currency_dialog_detected")
            raise CurrencyGuardTriggered("Premium currency dialog detected — confirmation required")

    def confirm(self) -> None:
        self._confirmed.set()

    def reset(self) -> None:
        self._confirmed.clear()


class UnknownScreenGuard:
    def __init__(self, enabled: bool = True):
        self._enabled = enabled

    def check(self, scene: dict[str, Any]) -> None:
        if not self._enabled:
            return
        screen = scene.get("screen", "unknown")
        confidence = scene.get("confidence", 1.0)
        if screen == "unknown" or confidence < 0.3:
            log.warning("guard.unknown_screen", screen=screen, confidence=confidence)
            raise UnknownScreenGuardTriggered(
                f"Unknown screen (screen={screen}, confidence={confidence})"
            )


class BoundsChecker:
    @staticmethod
    def check_point(x: float, y: float) -> None:
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise BoundsError(f"Coordinates out of bounds: ({x}, {y})")

    @staticmethod
    def check_tool_call(name: str, arguments: dict[str, Any]) -> None:
        if name == "tap":
            BoundsChecker.check_point(arguments.get("x", 0), arguments.get("y", 0))
        elif name == "swipe":
            BoundsChecker.check_point(
                arguments.get("start_x", 0), arguments.get("start_y", 0)
            )
            BoundsChecker.check_point(
                arguments.get("end_x", 0), arguments.get("end_y", 0)
            )
