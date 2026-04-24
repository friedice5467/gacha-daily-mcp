from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.server.database import get_database

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class StepIn(BaseModel):
    name: str
    vision_prompt: str
    conditions: list[dict[str, Any]]
    on_match: str | dict[str, Any]
    on_fail: str | dict[str, Any]
    max_retries: int = 5
    timeout_seconds: int = 60


class TaskCreateIn(BaseModel):
    game_package: str
    name: str
    steps: list[StepIn] = Field(default_factory=list)


class TaskUpdateIn(BaseModel):
    name: str | None = None
    enabled: bool | None = None


@router.get("")
async def list_tasks() -> list[dict[str, Any]]:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute(
            """SELECT t.*, COUNT(ts.id) as step_count
               FROM tasks t LEFT JOIN task_steps ts ON t.id = ts.task_id
               GROUP BY t.id ORDER BY t.created_at DESC"""
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.get("/{task_id}")
async def get_task(task_id: str) -> dict[str, Any]:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task_row = await cursor.fetchone()
        if task_row is None:
            raise HTTPException(status_code=404, detail="Task not found")

        cursor = await conn.execute(
            "SELECT * FROM task_steps WHERE task_id = ? ORDER BY sort_order", (task_id,)
        )
        step_rows = await cursor.fetchall()

    task = dict(task_row)
    task["steps"] = []
    for row in step_rows:
        step = dict(row)
        step["conditions"] = json.loads(step["conditions"])
        step["on_match"] = json.loads(step["on_match"]) if step["on_match"].startswith("{") else step["on_match"]
        step["on_fail"] = json.loads(step["on_fail"]) if step["on_fail"].startswith("{") else step["on_fail"]
        task["steps"].append(step)
    return task


@router.post("")
async def create_task(body: TaskCreateIn) -> dict[str, Any]:
    task_id = str(uuid.uuid4())
    db = get_database()
    async with db.get_db() as conn:
        await conn.execute(
            "INSERT INTO tasks (id, game_package, name) VALUES (?, ?, ?)",
            (task_id, body.game_package, body.name),
        )
        for i, step in enumerate(body.steps):
            step_id = str(uuid.uuid4())
            on_match = json.dumps(step.on_match) if isinstance(step.on_match, dict) else step.on_match
            on_fail = json.dumps(step.on_fail) if isinstance(step.on_fail, dict) else step.on_fail
            await conn.execute(
                """INSERT INTO task_steps (id, task_id, sort_order, name, vision_prompt, conditions, on_match, on_fail, max_retries, timeout_seconds)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (step_id, task_id, i, step.name, step.vision_prompt, json.dumps(step.conditions), on_match, on_fail, step.max_retries, step.timeout_seconds),
            )
        await conn.commit()
    return {"id": task_id}


@router.put("/{task_id}")
async def update_task(task_id: str, body: TaskUpdateIn) -> dict[str, str]:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Task not found")

        updates = []
        params: list[Any] = []
        if body.name is not None:
            updates.append("name = ?")
            params.append(body.name)
        if body.enabled is not None:
            updates.append("enabled = ?")
            params.append(int(body.enabled))
        if updates:
            updates.append("updated_at = datetime('now')")
            params.append(task_id)
            await conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
            await conn.commit()
    return {"status": "ok"}


@router.delete("/{task_id}")
async def delete_task(task_id: str) -> dict[str, str]:
    db = get_database()
    async with db.get_db() as conn:
        await conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await conn.commit()
    return {"status": "ok"}


@router.put("/{task_id}/steps")
async def replace_steps(task_id: str, steps: list[StepIn]) -> dict[str, str]:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Task not found")

        await conn.execute("DELETE FROM task_steps WHERE task_id = ?", (task_id,))
        for i, step in enumerate(steps):
            step_id = str(uuid.uuid4())
            on_match = json.dumps(step.on_match) if isinstance(step.on_match, dict) else step.on_match
            on_fail = json.dumps(step.on_fail) if isinstance(step.on_fail, dict) else step.on_fail
            await conn.execute(
                """INSERT INTO task_steps (id, task_id, sort_order, name, vision_prompt, conditions, on_match, on_fail, max_retries, timeout_seconds)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (step_id, task_id, i, step.name, step.vision_prompt, json.dumps(step.conditions), on_match, on_fail, step.max_retries, step.timeout_seconds),
            )
        await conn.execute("UPDATE tasks SET updated_at = datetime('now') WHERE id = ?", (task_id,))
        await conn.commit()
    return {"status": "ok"}


@router.post("/{task_id}/duplicate")
async def duplicate_task(task_id: str) -> dict[str, str]:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task_row = await cursor.fetchone()
        if task_row is None:
            raise HTTPException(status_code=404, detail="Task not found")

        new_task_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO tasks (id, game_package, name) VALUES (?, ?, ?)",
            (new_task_id, task_row["game_package"], f"{task_row['name']} (copy)"),
        )

        cursor = await conn.execute(
            "SELECT * FROM task_steps WHERE task_id = ? ORDER BY sort_order", (task_id,)
        )
        step_rows = await cursor.fetchall()
        for row in step_rows:
            new_step_id = str(uuid.uuid4())
            await conn.execute(
                """INSERT INTO task_steps (id, task_id, sort_order, name, vision_prompt, conditions, on_match, on_fail, max_retries, timeout_seconds)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (new_step_id, new_task_id, row["sort_order"], row["name"], row["vision_prompt"], row["conditions"], row["on_match"], row["on_fail"], row["max_retries"], row["timeout_seconds"]),
            )
        await conn.commit()
    return {"id": new_task_id}
