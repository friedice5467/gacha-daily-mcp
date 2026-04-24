from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.dashboard.routes.config import router as config_router
from src.dashboard.routes.games import router as games_router
from src.dashboard.routes.runs import router as runs_router
from src.dashboard.routes.schedules import router as schedules_router
from src.dashboard.routes.status import router as status_router
from src.dashboard.routes.tasks import router as tasks_router


def create_dashboard() -> FastAPI:
    app = FastAPI(title="gacha-mcp-dashboard")

    app.include_router(config_router)
    app.include_router(games_router)
    app.include_router(runs_router)
    app.include_router(schedules_router)
    app.include_router(status_router)
    app.include_router(tasks_router)

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
