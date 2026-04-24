from __future__ import annotations

import structlog

from src.llm.base import LLMAdapter, LLMNotConfiguredError
from src.llm.claude import ClaudeAdapter
from src.llm.openai_compat import OpenAICompatAdapter
from src.server.database import get_database

log = structlog.get_logger()


async def get_adapter(role: str) -> LLMAdapter:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute(
            "SELECT * FROM llm_config WHERE role = ? LIMIT 1", (role,)
        )
        row = await cursor.fetchone()

    if row is None:
        raise LLMNotConfiguredError(f"No LLM configured for role '{role}'")

    backend = row["backend"]
    model = row["model"]
    max_tokens = row["max_tokens"]

    if backend == "claude":
        if not row["api_key"]:
            raise LLMNotConfiguredError(f"API key missing for Claude ({role})")
        return ClaudeAdapter(model=model, api_key=row["api_key"], max_tokens=max_tokens)

    if backend == "openai_compat":
        if not row["base_url"]:
            raise LLMNotConfiguredError(f"Base URL missing for OpenAI-compat ({role})")
        return OpenAICompatAdapter(
            model=model,
            base_url=row["base_url"],
            api_key=row["api_key"] or "not-needed",
            max_tokens=max_tokens,
            tool_calling_mode=row["tool_calling_mode"] or "native",
        )

    raise LLMNotConfiguredError(f"Unknown backend '{backend}' for role '{role}'")
