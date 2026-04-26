from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/status", tags=["status"])

_current_run: dict[str, Any] | None = None


def set_current_run(run_info: dict[str, Any] | None) -> None:
    global _current_run
    _current_run = run_info


@router.get("")
async def get_status() -> dict[str, Any]:
    import src.server.main as _main

    if _main._adb_client is None:
        await _main._reconnect_adb()

    return {
        "adb_connected": _main._adb_client is not None,
        "current_run": _current_run,
    }


@router.post("/stop")
async def stop_task() -> dict[str, str]:
    from src.server.main import _emergency_stop

    if _emergency_stop is not None:
        _emergency_stop.trigger()
    return {"status": "ok"}


@router.get("/logs/stream")
async def stream_logs() -> StreamingResponse:
    from src.server.log_buffer import recent, subscribe, unsubscribe

    async def _generate():
        for line in recent():
            yield f"data: {line}\n\n"
        q = subscribe()
        try:
            while True:
                try:
                    line = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {line}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe(q)

    return StreamingResponse(_generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/run/{task_id}")
async def run_task_endpoint(task_id: str) -> dict[str, str]:
    import asyncio

    from src.server.main import _start_task_run

    asyncio.create_task(_start_task_run(task_id))
    return {"status": "started", "task_id": task_id}
