from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.server.database import get_database

router = APIRouter(prefix="/api/games", tags=["games"])


class GameIn(BaseModel):
    package_name: str
    display_name: str
    vision_system_prompt: str = ""


class GameUpdateIn(BaseModel):
    display_name: str | None = None
    vision_system_prompt: str | None = None
    active: bool | None = None


@router.get("")
async def list_games() -> list[dict[str, Any]]:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM games ORDER BY display_name")
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.post("")
async def add_game(body: GameIn) -> dict[str, str]:
    db = get_database()
    async with db.get_db() as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO games (package_name, display_name, vision_system_prompt) VALUES (?, ?, ?)",
            (body.package_name, body.display_name, body.vision_system_prompt),
        )
        await conn.commit()
    return {"status": "ok", "package_name": body.package_name}


@router.put("/{package_name}")
async def update_game(package_name: str, body: GameUpdateIn) -> dict[str, str]:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT package_name FROM games WHERE package_name = ?", (package_name,))
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Game not found")

        updates = []
        params: list[Any] = []
        if body.display_name is not None:
            updates.append("display_name = ?")
            params.append(body.display_name)
        if body.vision_system_prompt is not None:
            updates.append("vision_system_prompt = ?")
            params.append(body.vision_system_prompt)
        if body.active is not None:
            updates.append("active = ?")
            params.append(int(body.active))
        if updates:
            params.append(package_name)
            await conn.execute(f"UPDATE games SET {', '.join(updates)} WHERE package_name = ?", params)
            await conn.commit()
    return {"status": "ok"}


@router.delete("/{package_name}")
async def delete_game(package_name: str) -> dict[str, str]:
    db = get_database()
    async with db.get_db() as conn:
        await conn.execute("DELETE FROM games WHERE package_name = ?", (package_name,))
        await conn.commit()
    return {"status": "ok"}
