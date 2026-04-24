from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api/status", tags=["status"])

_current_run: dict[str, Any] | None = None


def set_current_run(run_info: dict[str, Any] | None) -> None:
    global _current_run
    _current_run = run_info


@router.get("")
async def get_status() -> dict[str, Any]:
    from src.server.main import _adb_client

    return {
        "adb_connected": _adb_client is not None,
        "current_run": _current_run,
    }


@router.post("/stop")
async def stop_task() -> dict[str, str]:
    from src.server.main import _emergency_stop

    if _emergency_stop is not None:
        _emergency_stop.trigger()
    return {"status": "ok"}


@router.post("/run/{task_id}")
async def run_task_endpoint(task_id: str) -> dict[str, str]:
    import asyncio

    from src.server.main import _start_task_run

    asyncio.create_task(_start_task_run(task_id))
    return {"status": "started", "task_id": task_id}
