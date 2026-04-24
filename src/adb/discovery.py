from __future__ import annotations

import asyncio
from functools import partial

import structlog
from adbutils import AdbClient, AdbDevice

from src.adb.client import ADBClient, DeviceNotConnectedError

log = structlog.get_logger()

DEFAULT_ADB_HOST = "host.docker.internal"
DEFAULT_ADB_PORT = 5555


async def connect_device(
    host: str = DEFAULT_ADB_HOST,
    port: int = DEFAULT_ADB_PORT,
    screen_width: int = 1280,
    screen_height: int = 720,
) -> ADBClient:
    loop = asyncio.get_running_loop()
    adb = AdbClient()

    addr = f"{host}:{port}"
    log.info("adb.connecting", addr=addr)
    try:
        await loop.run_in_executor(None, partial(adb.connect, addr))
    except Exception as exc:
        raise DeviceNotConnectedError(f"Failed to connect to {addr}: {exc}") from exc

    device = await _find_device(adb, addr)
    log.info("adb.connected", serial=device.serial)
    return ADBClient(device, screen_width, screen_height)


async def list_devices() -> list[str]:
    loop = asyncio.get_running_loop()
    adb = AdbClient()
    devices: list[AdbDevice] = await loop.run_in_executor(None, adb.device_list)
    return [d.serial for d in devices]


async def _find_device(adb: AdbClient, preferred_addr: str) -> AdbDevice:
    loop = asyncio.get_running_loop()
    devices: list[AdbDevice] = await loop.run_in_executor(None, adb.device_list)

    if not devices:
        raise DeviceNotConnectedError("No ADB devices found")

    for d in devices:
        if d.serial == preferred_addr:
            return d

    return devices[0]
