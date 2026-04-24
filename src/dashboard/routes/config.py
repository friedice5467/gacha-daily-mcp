from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.server.database import get_database

router = APIRouter(prefix="/api/config", tags=["config"])


class LLMConfigIn(BaseModel):
    id: str
    role: str
    backend: str
    model: str
    base_url: str | None = None
    api_key: str | None = None
    max_tokens: int = 1024
    tool_calling_mode: str = "native"


class ADBConfigIn(BaseModel):
    host: str = "host.docker.internal"
    port: int = 5555
    screenshot_width: int = 1280
    screenshot_height: int = 720
    screenshot_interval_ms: int = 500


class SafetyConfigIn(BaseModel):
    max_actions_per_minute: int = 20
    max_actions_per_invocation: int = 50
    cooldown_seconds: float = 2.0
    confirm_premium_currency: bool = True
    confirm_sell_discard: bool = True
    confirm_unknown_screen: bool = True
    emergency_stop_key: str = "ctrl+shift+q"


@router.get("/llm")
async def list_llm_configs() -> list[dict[str, Any]]:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM llm_config ORDER BY role")
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.get("/llm/{config_id}")
async def get_llm_config(config_id: str) -> dict[str, Any]:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM llm_config WHERE id = ?", (config_id,))
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="LLM config not found")
    return dict(row)


@router.put("/llm/{config_id}")
async def upsert_llm_config(config_id: str, body: LLMConfigIn) -> dict[str, Any]:
    db = get_database()
    async with db.get_db() as conn:
        await conn.execute(
            """INSERT INTO llm_config (id, role, backend, model, base_url, api_key, max_tokens, tool_calling_mode, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(id) DO UPDATE SET
                 role=excluded.role, backend=excluded.backend, model=excluded.model,
                 base_url=excluded.base_url, api_key=excluded.api_key,
                 max_tokens=excluded.max_tokens, tool_calling_mode=excluded.tool_calling_mode,
                 updated_at=datetime('now')""",
            (config_id, body.role, body.backend, body.model, body.base_url, body.api_key, body.max_tokens, body.tool_calling_mode),
        )
        await conn.commit()
    return {"status": "ok", "id": config_id}


@router.delete("/llm/{config_id}")
async def delete_llm_config(config_id: str) -> dict[str, str]:
    db = get_database()
    async with db.get_db() as conn:
        await conn.execute("DELETE FROM llm_config WHERE id = ?", (config_id,))
        await conn.commit()
    return {"status": "ok"}


@router.get("/adb")
async def get_adb_config() -> dict[str, Any]:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM adb_config WHERE id = 1")
        row = await cursor.fetchone()
    return dict(row)


@router.put("/adb")
async def update_adb_config(body: ADBConfigIn) -> dict[str, str]:
    db = get_database()
    async with db.get_db() as conn:
        await conn.execute(
            """UPDATE adb_config SET host=?, port=?, screenshot_width=?,
               screenshot_height=?, screenshot_interval_ms=? WHERE id=1""",
            (body.host, body.port, body.screenshot_width, body.screenshot_height, body.screenshot_interval_ms),
        )
        await conn.commit()
    return {"status": "ok"}


@router.get("/safety")
async def get_safety_config() -> dict[str, Any]:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM safety_config WHERE id = 1")
        row = await cursor.fetchone()
    return dict(row)


@router.put("/safety")
async def update_safety_config(body: SafetyConfigIn) -> dict[str, str]:
    db = get_database()
    async with db.get_db() as conn:
        await conn.execute(
            """UPDATE safety_config SET max_actions_per_minute=?, max_actions_per_invocation=?,
               cooldown_seconds=?, confirm_premium_currency=?, confirm_sell_discard=?,
               confirm_unknown_screen=?, emergency_stop_key=? WHERE id=1""",
            (
                body.max_actions_per_minute, body.max_actions_per_invocation,
                body.cooldown_seconds, int(body.confirm_premium_currency),
                int(body.confirm_sell_discard), int(body.confirm_unknown_screen),
                body.emergency_stop_key,
            ),
        )
        await conn.commit()
    return {"status": "ok"}
