from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from src.server.database import Database, DatabaseError


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


async def test_creates_database_file(tmp_path: Path) -> None:
    db_path = tmp_path / "new.db"
    database = Database(db_path)
    await database.connect()
    assert db_path.exists()
    await database.close()


async def test_all_tables_exist(db: Database) -> None:
    expected_tables = {
        "schema_version",
        "llm_config",
        "adb_config",
        "safety_config",
        "games",
        "tasks",
        "task_steps",
        "schedules",
        "task_memory",
        "run_log",
    }
    async with db.get_db() as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        rows = await cursor.fetchall()
    table_names = {row["name"] for row in rows}
    assert expected_tables == table_names


async def test_seed_adb_config(db: Database) -> None:
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM adb_config WHERE id = 1")
        row = await cursor.fetchone()
    assert row is not None
    assert row["host"] == "host.docker.internal"
    assert row["port"] == 5555


async def test_seed_safety_config(db: Database) -> None:
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM safety_config WHERE id = 1")
        row = await cursor.fetchone()
    assert row is not None
    assert row["max_actions_per_minute"] == 20
    assert row["cooldown_seconds"] == 2.0


async def test_seed_schema_version(db: Database) -> None:
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT version FROM schema_version")
        row = await cursor.fetchone()
    assert row is not None
    assert row["version"] == 1


async def test_foreign_keys_enabled(db: Database) -> None:
    async with db.get_db() as conn:
        cursor = await conn.execute("PRAGMA foreign_keys")
        row = await cursor.fetchone()
    assert row[0] == 1


async def test_insert_and_query_game(db: Database) -> None:
    async with db.get_db() as conn:
        await conn.execute(
            "INSERT INTO games (package_name, display_name) VALUES (?, ?)",
            ("com.example.game", "Example Game"),
        )
        await conn.commit()
        cursor = await conn.execute(
            "SELECT * FROM games WHERE package_name = ?", ("com.example.game",)
        )
        row = await cursor.fetchone()
    assert row["display_name"] == "Example Game"
    assert row["active"] == 0
    assert row["vision_system_prompt"] == ""


async def test_insert_task_with_steps(db: Database) -> None:
    task_id = str(uuid.uuid4())
    step_id = str(uuid.uuid4())
    async with db.get_db() as conn:
        await conn.execute(
            "INSERT INTO games (package_name, display_name) VALUES (?, ?)",
            ("com.test.game", "Test"),
        )
        await conn.execute(
            "INSERT INTO tasks (id, game_package, name) VALUES (?, ?, ?)",
            (task_id, "com.test.game", "Daily quest"),
        )
        await conn.execute(
            "INSERT INTO task_steps (id, task_id, sort_order, name, vision_prompt, conditions, on_match, on_fail) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                step_id,
                task_id,
                1,
                "Wait for menu",
                "Is this the main menu?",
                json.dumps([{"field": "screen", "op": "eq", "value": "main_menu"}]),
                "next",
                "retry",
            ),
        )
        await conn.commit()
        cursor = await conn.execute(
            "SELECT * FROM task_steps WHERE task_id = ?", (task_id,)
        )
        row = await cursor.fetchone()
    assert row["name"] == "Wait for menu"
    assert row["sort_order"] == 1


async def test_cascade_delete(db: Database) -> None:
    task_id = str(uuid.uuid4())
    step_id = str(uuid.uuid4())
    async with db.get_db() as conn:
        await conn.execute(
            "INSERT INTO games (package_name, display_name) VALUES (?, ?)",
            ("com.cascade.game", "Cascade"),
        )
        await conn.execute(
            "INSERT INTO tasks (id, game_package, name) VALUES (?, ?, ?)",
            (task_id, "com.cascade.game", "Test task"),
        )
        await conn.execute(
            "INSERT INTO task_steps (id, task_id, sort_order, name, vision_prompt, conditions, on_match, on_fail) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (step_id, task_id, 1, "Step 1", "prompt", "[]", "next", "retry"),
        )
        await conn.commit()
        await conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await conn.commit()
        cursor = await conn.execute(
            "SELECT COUNT(*) as cnt FROM task_steps WHERE task_id = ?", (task_id,)
        )
        row = await cursor.fetchone()
    assert row["cnt"] == 0


async def test_run_log_insert(db: Database) -> None:
    async with db.get_db() as conn:
        await conn.execute(
            "INSERT INTO run_log (action, details) VALUES (?, ?)",
            ("screenshot", "captured frame"),
        )
        await conn.commit()
        cursor = await conn.execute("SELECT * FROM run_log ORDER BY id DESC LIMIT 1")
        row = await cursor.fetchone()
    assert row["action"] == "screenshot"
    assert row["created_at"] is not None


async def test_idempotent_connect(tmp_path: Path) -> None:
    db_path = tmp_path / "idempotent.db"
    database = Database(db_path)
    await database.connect()
    await database.close()
    database2 = Database(db_path)
    await database2.connect()
    async with database2.get_db() as conn:
        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM schema_version")
        row = await cursor.fetchone()
    assert row["cnt"] == 1
    await database2.close()


async def test_get_db_without_connect_raises() -> None:
    database = Database(Path("/tmp/nope.db"))
    with pytest.raises(DatabaseError):
        async with database.get_db() as _:
            pass
