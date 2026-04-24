from __future__ import annotations

import asyncio

import structlog

log = structlog.get_logger()


class EmergencyStop:
    def __init__(self):
        self._stop_event = asyncio.Event()

    def trigger(self) -> None:
        log.warning("emergency.stop_triggered")
        self._stop_event.set()

    def reset(self) -> None:
        self._stop_event.clear()

    @property
    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    async def check(self) -> None:
        if self._stop_event.is_set():
            raise EmergencyStopError("Emergency stop activated")


class EmergencyStopError(Exception):
    pass
