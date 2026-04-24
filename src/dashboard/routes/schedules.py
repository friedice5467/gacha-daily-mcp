from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.server.database import get_database

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


class ScheduleIn(BaseModel):
    task_id: str
    cron: str
    enabled: bool = True


class ScheduleUpdateIn(BaseModel):
    cron: str | None = None
    enabled: bool | None = None


@router.get("")
async def list_schedules() -> list[dict[str, Any]]:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute(
            """SELECT s.*, t.name as task_name FROM schedules s
               LEFT JOIN tasks t ON s.task_id = t.id ORDER BY s.task_id"""
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.post("")
async def create_schedule(body: ScheduleIn) -> dict[str, str]:
    schedule_id = str(uuid.uuid4())
    db = get_database()
    async with db.get_db() as conn:
        await conn.execute(
            "INSERT INTO schedules (id, task_id, cron, enabled) VALUES (?, ?, ?, ?)",
            (schedule_id, body.task_id, body.cron, int(body.enabled)),
        )
        await conn.commit()
    return {"id": schedule_id}


@router.put("/{schedule_id}")
async def update_schedule(schedule_id: str, body: ScheduleUpdateIn) -> dict[str, str]:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT id FROM schedules WHERE id = ?", (schedule_id,))
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Schedule not found")

        updates = []
        params: list[Any] = []
        if body.cron is not None:
            updates.append("cron = ?")
            params.append(body.cron)
        if body.enabled is not None:
            updates.append("enabled = ?")
            params.append(int(body.enabled))
        if updates:
            params.append(schedule_id)
            await conn.execute(f"UPDATE schedules SET {', '.join(updates)} WHERE id = ?", params)
            await conn.commit()
    return {"status": "ok"}


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str) -> dict[str, str]:
    db = get_database()
    async with db.get_db() as conn:
        await conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        await conn.commit()
    return {"status": "ok"}
