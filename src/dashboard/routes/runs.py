from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.server.database import get_database

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("")
async def list_runs(task_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    db = get_database()
    async with db.get_db() as conn:
        if task_id:
            cursor = await conn.execute(
                "SELECT * FROM run_log WHERE task_id = ? ORDER BY id DESC LIMIT ?",
                (task_id, limit),
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM run_log ORDER BY id DESC LIMIT ?", (limit,)
            )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.delete("")
async def clear_runs(task_id: str | None = None) -> dict[str, str]:
    db = get_database()
    async with db.get_db() as conn:
        if task_id:
            await conn.execute("DELETE FROM run_log WHERE task_id = ?", (task_id,))
        else:
            await conn.execute("DELETE FROM run_log")
        await conn.commit()
    return {"status": "ok"}
