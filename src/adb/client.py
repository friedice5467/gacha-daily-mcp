from __future__ import annotations

import asyncio
import io
from functools import partial
from typing import TYPE_CHECKING

import structlog
from PIL import Image

from src.adb.coords import ADBError, NormalizedPoint, NormalizedSwipe, PixelPoint

if TYPE_CHECKING:
    from adbutils import AdbDevice

log = structlog.get_logger()


class DeviceNotConnectedError(ADBError):
    pass


class ADBClient:
    def __init__(self, device: AdbDevice, width: int = 1280, height: int = 720):
        self._device = device
        self._width = width
        self._height = height

    @property
    def serial(self) -> str:
        return self._device.serial

    @property
    def screen_size(self) -> tuple[int, int]:
        return self._width, self._height

    async def screenshot(self) -> bytes:
        loop = asyncio.get_running_loop()
        img = await loop.run_in_executor(None, self._device.screenshot)
        if img.size != (self._width, self._height):
            img = img.resize((self._width, self._height), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    async def tap(self, point: NormalizedPoint) -> None:
        px = point.to_pixels(self._width, self._height)
        log.debug("adb.tap", x=px.x, y=px.y)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, partial(self._device.click, px.x, px.y))

    async def swipe(self, swipe: NormalizedSwipe) -> None:
        ps = swipe.to_pixels(self._width, self._height)
        log.debug(
            "adb.swipe",
            sx=ps.start.x,
            sy=ps.start.y,
            ex=ps.end.x,
            ey=ps.end.y,
            duration=ps.duration_ms,
        )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            partial(
                self._device.swipe,
                ps.start.x,
                ps.start.y,
                ps.end.x,
                ps.end.y,
                ps.duration_ms / 1000.0,
            ),
        )

    async def key_event(self, keycode: int) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, partial(self._device.keyevent, keycode)
        )

    async def launch_app(self, package: str) -> None:
        log.info("adb.launch_app", package=package)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            partial(
                self._device.shell,
                f"monkey -p {package} -c android.intent.category.LAUNCHER 1",
            ),
        )

    async def current_app(self) -> str | None:
        loop = asyncio.get_running_loop()
        output = await loop.run_in_executor(
            None,
            partial(self._device.shell, "dumpsys activity activities | grep mResumedActivity"),
        )
        if not output:
            return None
        for part in output.split():
            if "/" in part and "." in part:
                return part.split("/")[0]
        return None

    async def list_packages(self) -> list[str]:
        loop = asyncio.get_running_loop()
        output = await loop.run_in_executor(
            None, partial(self._device.shell, "pm list packages -3")
        )
        return [
            line.replace("package:", "").strip()
            for line in output.splitlines()
            if line.startswith("package:")
        ]

    async def wait_idle(self, timeout: float = 5.0) -> None:
        await asyncio.sleep(min(timeout, 0.5))
