from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import structlog
import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool

from src.server.database import get_database, init_database
from src.tools import ALL_TOOLS

log = structlog.get_logger()

PORT = 8420

mcp_server = Server("gacha-mcp")


@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name=t["name"],
            description=t.get("description", ""),
            inputSchema=t["parameters"],
        )
        for t in ALL_TOOLS
    ]


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    result = await _dispatch_tool(name, arguments)
    return [TextContent(type="text", text=json.dumps(result))]


async def _dispatch_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from src.adb.coords import NormalizedPoint, NormalizedSwipe

    if name == "screenshot":
        return await _handle_screenshot()
    if name == "analyze_screen":
        return await _handle_analyze_screen(arguments)
    if name == "tap":
        client = _get_adb_client()
        point = NormalizedPoint(x=arguments["x"], y=arguments["y"])
        await client.tap(point)
        return {"status": "ok"}
    if name == "swipe":
        client = _get_adb_client()
        swipe = NormalizedSwipe(
            start=NormalizedPoint(x=arguments["start_x"], y=arguments["start_y"]),
            end=NormalizedPoint(x=arguments["end_x"], y=arguments["end_y"]),
            duration_ms=arguments.get("duration_ms", 300),
        )
        await client.swipe(swipe)
        return {"status": "ok"}
    if name == "wait":
        await asyncio.sleep(arguments["seconds"])
        return {"status": "ok"}
    if name == "key_event":
        client = _get_adb_client()
        await client.key_event(arguments["keycode"])
        return {"status": "ok"}
    if name == "launch_app":
        client = _get_adb_client()
        await client.launch_app(arguments["package"])
        return {"status": "ok"}
    if name == "current_app":
        client = _get_adb_client()
        pkg = await client.current_app()
        return {"package": pkg}
    if name == "list_packages":
        client = _get_adb_client()
        packages = await client.list_packages()
        return {"packages": packages}
    if name == "memory_get":
        return await _handle_memory_get(arguments["key"])
    if name == "memory_set":
        return await _handle_memory_set(arguments["key"], arguments["value"])
    if name == "memory_delete":
        return await _handle_memory_delete(arguments["key"])
    if name == "memory_list":
        return await _handle_memory_list()

    return {"error": f"Unknown tool: {name}"}


_adb_client = None
_emergency_stop = None


def set_adb_client(client: Any) -> None:
    global _adb_client
    _adb_client = client


def _get_adb_client() -> Any:
    from src.adb.client import DeviceNotConnectedError

    if _adb_client is None:
        raise DeviceNotConnectedError("ADB client not connected")
    return _adb_client


async def _handle_screenshot() -> dict[str, Any]:
    client = _get_adb_client()
    png_bytes = await client.screenshot()
    b64 = base64.standard_b64encode(png_bytes).decode("ascii")
    w, h = client.screen_size
    return {"image_base64": b64, "width": w, "height": h}


async def _handle_analyze_screen(arguments: dict[str, Any]) -> dict[str, Any]:
    from src.engine.vision import SceneState, TaskStep, analyze_screen
    from src.llm.factory import get_adapter

    client = _get_adb_client()
    png_bytes = await client.screenshot()
    adapter = await get_adapter("vision")

    prompt = arguments.get("prompt", "Describe the current screen.")
    step = TaskStep(
        name="manual_analyze",
        vision_prompt=prompt,
        conditions=[],
        on_match="complete",
        on_fail="complete",
    )

    game_context = await _get_active_game_context()
    scene = await analyze_screen(png_bytes, step, adapter, game_context=game_context)
    return scene.model_dump(exclude_none=True)


async def _get_active_game_context() -> str:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute(
            "SELECT vision_system_prompt FROM games WHERE active = 1 LIMIT 1"
        )
        row = await cursor.fetchone()
    if row and row["vision_system_prompt"]:
        return row["vision_system_prompt"]
    return ""


async def _handle_memory_get(key: str) -> dict[str, Any]:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT value FROM task_memory WHERE key = ?", (key,))
        row = await cursor.fetchone()
    if row is None:
        return {"key": key, "value": None}
    return {"key": key, "value": row["value"]}


async def _handle_memory_set(key: str, value: str) -> dict[str, Any]:
    db = get_database()
    async with db.get_db() as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO task_memory (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            (key, value),
        )
        await conn.commit()
    return {"status": "ok"}


async def _handle_memory_delete(key: str) -> dict[str, Any]:
    db = get_database()
    async with db.get_db() as conn:
        await conn.execute("DELETE FROM task_memory WHERE key = ?", (key,))
        await conn.commit()
    return {"status": "ok"}


async def _handle_memory_list() -> dict[str, Any]:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT key FROM task_memory ORDER BY key")
        rows = await cursor.fetchall()
    return {"keys": [row["key"] for row in rows]}


def create_app():
    from pathlib import Path

    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    from src.dashboard.routes.config import router as config_router
    from src.dashboard.routes.games import router as games_router
    from src.dashboard.routes.runs import router as runs_router
    from src.dashboard.routes.schedules import router as schedules_router
    from src.dashboard.routes.status import router as status_router
    from src.dashboard.routes.tasks import router as tasks_router

    app = FastAPI(title="gacha-mcp")

    sse = SseServerTransport("/mcp/messages/")

    @app.get("/mcp/sse")
    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await mcp_server.run(
                streams[0], streams[1], mcp_server.create_initialization_options()
            )

    @app.post("/mcp/messages/")
    async def handle_messages(request):
        await sse.handle_post_message(request.scope, request.receive, request._send)

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "adb_connected": _adb_client is not None}

    app.include_router(config_router)
    app.include_router(games_router)
    app.include_router(runs_router)
    app.include_router(schedules_router)
    app.include_router(status_router)
    app.include_router(tasks_router)

    static_dir = Path(__file__).parent.parent / "dashboard" / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


async def _start_task_run(task_id: str) -> None:
    from src.dashboard.routes.status import set_current_run
    from src.engine.loop import run_task
    from src.llm.factory import get_adapter
    from src.safety.emergency import EmergencyStop
    from src.safety.guards import CurrencyGuard, UnknownScreenGuard
    from src.safety.rate_limiter import RateLimiter

    global _emergency_stop

    client = _get_adb_client()
    _emergency_stop = EmergencyStop()

    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM safety_config WHERE id = 1")
        safety = dict(await cursor.fetchone())

    set_current_run({"task_id": task_id, "status": "running"})
    try:
        result = await run_task(
            task_id=task_id,
            adb_client=client,
            vision_adapter=await get_adapter("vision"),
            action_adapter=await get_adapter("action"),
            rate_limiter=RateLimiter(max_per_minute=safety["max_actions_per_minute"]),
            emergency_stop=_emergency_stop,
            currency_guard=CurrencyGuard(enabled=bool(safety["confirm_premium_currency"])),
            unknown_guard=UnknownScreenGuard(enabled=bool(safety["confirm_unknown_screen"])),
            tool_handler=_dispatch_tool,
        )
        set_current_run({"task_id": task_id, "status": "completed", "success": result.success})
    except Exception as exc:
        log.error("task_run.failed", task_id=task_id, error=str(exc))
        set_current_run({"task_id": task_id, "status": "failed", "error": str(exc)})


async def main() -> None:
    global _emergency_stop

    db = await init_database()
    log.info("server.starting", port=PORT)
    _emergency_stop = None

    try:
        adb_config = await _load_adb_config()
        from src.adb.discovery import connect_device

        client = await connect_device(
            host=adb_config["host"],
            port=adb_config["port"],
            screen_width=adb_config["screenshot_width"],
            screen_height=adb_config["screenshot_height"],
        )
        set_adb_client(client)
    except Exception as exc:
        log.warning("server.adb_connect_failed", error=str(exc))

    from src.engine.scheduler import start_scheduler, stop_scheduler

    try:
        await start_scheduler()
    except Exception as exc:
        log.warning("server.scheduler_failed", error=str(exc))

    app = create_app()
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        stop_scheduler()


async def _load_adb_config() -> dict[str, Any]:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM adb_config WHERE id = 1")
        row = await cursor.fetchone()
    return dict(row)


if __name__ == "__main__":
    asyncio.run(main())
