from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.server.database import Database, init_database
from src.server import database as db_mod


@pytest.fixture
async def client(tmp_path: Path):
    db = await init_database(tmp_path / "dash_test.db")
    original = db_mod._default_db
    try:
        from src.dashboard.app import create_dashboard
        app = create_dashboard()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        await db.close()
        db_mod._default_db = original


async def test_get_adb_config(client: AsyncClient) -> None:
    r = await client.get("/api/config/adb")
    assert r.status_code == 200
    data = r.json()
    assert data["host"] == "host.docker.internal"
    assert data["port"] == 5555


async def test_update_adb_config(client: AsyncClient) -> None:
    r = await client.put("/api/config/adb", json={"host": "localhost", "port": 5556})
    assert r.status_code == 200
    r = await client.get("/api/config/adb")
    assert r.json()["host"] == "localhost"
    assert r.json()["port"] == 5556


async def test_get_safety_config(client: AsyncClient) -> None:
    r = await client.get("/api/config/safety")
    assert r.status_code == 200
    assert r.json()["max_actions_per_minute"] == 20


async def test_update_safety_config(client: AsyncClient) -> None:
    r = await client.put("/api/config/safety", json={"max_actions_per_minute": 30})
    assert r.status_code == 200
    r = await client.get("/api/config/safety")
    assert r.json()["max_actions_per_minute"] == 30


async def test_llm_config_crud(client: AsyncClient) -> None:
    r = await client.put("/api/config/llm/v1", json={
        "id": "v1", "role": "vision", "backend": "claude",
        "model": "claude-sonnet-4-6", "api_key": "sk-test",
    })
    assert r.status_code == 200

    r = await client.get("/api/config/llm")
    assert len(r.json()) == 1
    assert r.json()[0]["model"] == "claude-sonnet-4-6"

    r = await client.get("/api/config/llm/v1")
    assert r.json()["role"] == "vision"

    r = await client.delete("/api/config/llm/v1")
    assert r.status_code == 200
    r = await client.get("/api/config/llm")
    assert len(r.json()) == 0


async def test_games_crud(client: AsyncClient) -> None:
    r = await client.post("/api/games", json={
        "package_name": "com.test.game",
        "display_name": "Test Game",
        "vision_system_prompt": "This is a test game.",
    })
    assert r.status_code == 200

    r = await client.get("/api/games")
    assert len(r.json()) == 1
    assert r.json()[0]["vision_system_prompt"] == "This is a test game."

    r = await client.put("/api/games/com.test.game", json={"active": True})
    assert r.status_code == 200

    r = await client.get("/api/games")
    assert r.json()[0]["active"] == 1

    r = await client.delete("/api/games/com.test.game")
    assert r.status_code == 200


async def test_tasks_crud(client: AsyncClient) -> None:
    await client.post("/api/games", json={
        "package_name": "com.test.game", "display_name": "Test",
    })

    r = await client.post("/api/tasks", json={
        "game_package": "com.test.game",
        "name": "Daily Quest",
        "steps": [
            {
                "name": "Wait for menu",
                "vision_prompt": "Is this the main menu?",
                "conditions": [{"field": "screen", "op": "eq", "value": "main_menu"}],
                "on_match": "next",
                "on_fail": "retry",
            }
        ],
    })
    assert r.status_code == 200
    task_id = r.json()["id"]

    r = await client.get("/api/tasks")
    assert len(r.json()) == 1
    assert r.json()[0]["step_count"] == 1

    r = await client.get(f"/api/tasks/{task_id}")
    assert r.json()["name"] == "Daily Quest"
    assert len(r.json()["steps"]) == 1

    r = await client.put(f"/api/tasks/{task_id}", json={"name": "Updated Quest"})
    assert r.status_code == 200

    r = await client.get(f"/api/tasks/{task_id}")
    assert r.json()["name"] == "Updated Quest"


async def test_task_duplicate(client: AsyncClient) -> None:
    await client.post("/api/games", json={
        "package_name": "com.dup.game", "display_name": "Dup",
    })
    r = await client.post("/api/tasks", json={
        "game_package": "com.dup.game", "name": "Original",
        "steps": [{"name": "S1", "vision_prompt": "p", "conditions": [], "on_match": "next", "on_fail": "retry"}],
    })
    task_id = r.json()["id"]

    r = await client.post(f"/api/tasks/{task_id}/duplicate")
    assert r.status_code == 200
    new_id = r.json()["id"]
    assert new_id != task_id

    r = await client.get(f"/api/tasks/{new_id}")
    assert r.json()["name"] == "Original (copy)"
    assert len(r.json()["steps"]) == 1


async def test_task_replace_steps(client: AsyncClient) -> None:
    await client.post("/api/games", json={
        "package_name": "com.steps.game", "display_name": "Steps",
    })
    r = await client.post("/api/tasks", json={
        "game_package": "com.steps.game", "name": "StepTask", "steps": [],
    })
    task_id = r.json()["id"]

    r = await client.put(f"/api/tasks/{task_id}/steps", json=[
        {"name": "New1", "vision_prompt": "p1", "conditions": [], "on_match": "next", "on_fail": "retry"},
        {"name": "New2", "vision_prompt": "p2", "conditions": [], "on_match": "complete", "on_fail": "abort"},
    ])
    assert r.status_code == 200

    r = await client.get(f"/api/tasks/{task_id}")
    assert len(r.json()["steps"]) == 2
    assert r.json()["steps"][0]["name"] == "New1"
    assert r.json()["steps"][1]["name"] == "New2"


async def test_task_delete_cascades(client: AsyncClient) -> None:
    await client.post("/api/games", json={
        "package_name": "com.del.game", "display_name": "Del",
    })
    r = await client.post("/api/tasks", json={
        "game_package": "com.del.game", "name": "ToDelete",
        "steps": [{"name": "S1", "vision_prompt": "p", "conditions": [], "on_match": "next", "on_fail": "retry"}],
    })
    task_id = r.json()["id"]

    r = await client.delete(f"/api/tasks/{task_id}")
    assert r.status_code == 200

    r = await client.get(f"/api/tasks/{task_id}")
    assert r.status_code == 404


async def test_schedules_crud(client: AsyncClient) -> None:
    await client.post("/api/games", json={
        "package_name": "com.sched.game", "display_name": "Sched",
    })
    r = await client.post("/api/tasks", json={
        "game_package": "com.sched.game", "name": "SchedTask", "steps": [],
    })
    task_id = r.json()["id"]

    r = await client.post("/api/schedules", json={
        "task_id": task_id, "cron": "0 6 * * *",
    })
    assert r.status_code == 200
    sched_id = r.json()["id"]

    r = await client.get("/api/schedules")
    assert len(r.json()) == 1

    r = await client.put(f"/api/schedules/{sched_id}", json={"enabled": False})
    assert r.status_code == 200

    r = await client.delete(f"/api/schedules/{sched_id}")
    assert r.status_code == 200


async def test_runs_list(client: AsyncClient) -> None:
    r = await client.get("/api/runs")
    assert r.status_code == 200
    assert r.json() == []
