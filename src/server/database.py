from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite
import structlog

log = structlog.get_logger()

DEFAULT_DB_PATH = Path("/data/gacha.db")
HOST_DB_PATH = Path.home() / "gacha-mcp" / "gacha.db"

CURRENT_SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS llm_config (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL CHECK (role IN ('vision', 'action')),
    backend TEXT NOT NULL CHECK (backend IN ('claude', 'openai_compat')),
    model TEXT NOT NULL,
    base_url TEXT,
    api_key TEXT,
    max_tokens INTEGER DEFAULT 1024,
    tool_calling_mode TEXT DEFAULT 'native',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS adb_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    host TEXT NOT NULL DEFAULT 'host.docker.internal',
    port INTEGER NOT NULL DEFAULT 5555,
    screenshot_width INTEGER DEFAULT 1280,
    screenshot_height INTEGER DEFAULT 720,
    screenshot_interval_ms INTEGER DEFAULT 500
);

CREATE TABLE IF NOT EXISTS safety_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    max_actions_per_minute INTEGER DEFAULT 20,
    max_actions_per_invocation INTEGER DEFAULT 50,
    cooldown_seconds REAL DEFAULT 2.0,
    confirm_premium_currency INTEGER DEFAULT 1,
    confirm_sell_discard INTEGER DEFAULT 1,
    confirm_unknown_screen INTEGER DEFAULT 1,
    emergency_stop_key TEXT DEFAULT 'ctrl+shift+q'
);

CREATE TABLE IF NOT EXISTS games (
    package_name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    vision_system_prompt TEXT DEFAULT '',
    active INTEGER DEFAULT 0,
    added_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    game_package TEXT NOT NULL REFERENCES games(package_name),
    name TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS task_steps (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    name TEXT NOT NULL,
    vision_prompt TEXT NOT NULL,
    conditions TEXT NOT NULL,
    on_match TEXT NOT NULL,
    on_fail TEXT NOT NULL,
    max_retries INTEGER DEFAULT 5,
    timeout_seconds INTEGER DEFAULT 60
);

CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    cron TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    last_run TEXT,
    next_run TEXT
);

CREATE TABLE IF NOT EXISTS task_memory (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT REFERENCES tasks(id),
    step_name TEXT,
    action TEXT NOT NULL,
    details TEXT,
    screenshot_hash TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

SEED_SQL = [
    "INSERT OR IGNORE INTO adb_config (id) VALUES (1)",
    "INSERT OR IGNORE INTO safety_config (id) VALUES (1)",
    "INSERT OR IGNORE INTO schema_version (version) VALUES (1)",
]


class DatabaseError(Exception):
    pass


class Database:
    def __init__(self, db_path: Path | None = None):
        if db_path is not None:
            self._path = db_path
        elif DEFAULT_DB_PATH.parent.exists():
            self._path = DEFAULT_DB_PATH
        else:
            self._path = HOST_DB_PATH
        self._lock = asyncio.Lock()
        self._connection: aiosqlite.Connection | None = None

    @property
    def path(self) -> Path:
        return self._path

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self._path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
        await self._init_schema()
        log.info("database.connected", path=str(self._path))

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None
            log.info("database.closed")

    async def _init_schema(self) -> None:
        assert self._connection is not None
        for statement in SCHEMA_SQL.split(";"):
            statement = statement.strip()
            if statement:
                await self._connection.execute(statement)
        for seed in SEED_SQL:
            await self._connection.execute(seed)
        await self._connection.commit()

    @asynccontextmanager
    async def get_db(self) -> AsyncIterator[aiosqlite.Connection]:
        if self._connection is None:
            raise DatabaseError("Database not connected. Call connect() first.")
        async with self._lock:
            yield self._connection


_default_db: Database | None = None


async def init_database(db_path: Path | None = None) -> Database:
    global _default_db
    _default_db = Database(db_path)
    await _default_db.connect()
    return _default_db


def get_database() -> Database:
    if _default_db is None:
        raise DatabaseError("Database not initialized. Call init_database() first.")
    return _default_db
