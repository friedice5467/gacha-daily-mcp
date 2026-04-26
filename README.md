# gacha-mcp

Don't have time to play your gacha games? Here's a solution, a Python MCP server that automates mobile game dailies on BlueStacks via ADB. Uses a dual-LLM architecture: one vision model reads the screen, a rule engine decides what to do, and an action model executes through ADB. Game-agnostic — works with any game by configuring task steps through a web dashboard.

All configuration lives in SQLite. No `.env` files.

## How it works

The system runs a loop for each task:

1. **Vision LLM** receives a screenshot and a per-step prompt. Returns structured JSON describing the screen (UI elements, positions, game state). Never issues actions.
2. **Rule engine** evaluates the vision output against user-defined conditions (field/operator/value expressions). Pure logic, no LLM.
3. **Action LLM** is only invoked when the rule engine triggers an `execute` action. It receives the goal, the current scene, and access to tools (tap, swipe, wait, etc.). Executes minimum actions, then yields control back.

Tasks are defined as ordered lists of steps. Each step has a vision prompt, conditions, and configurable match/fail behaviors (advance, retry, goto, abort, etc.). This means you can build complex automation flows without writing code.

### Safety

- Rate limiter (token bucket, configurable actions/minute)
- Coordinate bounds checking (rejects taps outside 0.0-1.0)
- Premium currency guard (blocks action LLM on purchase dialogs)
- Unknown screen guard (blocks on low-confidence vision results)
- Max actions per invocation
- Emergency stop (keyboard shortcut + dashboard button)

## Setup

### Prerequisites

- Python 3.12+
- BlueStacks with ADB enabled (default port 5555)
- An LLM API key (Claude, or a local model via LM Studio / Ollama)

### Docker

```bash
git clone https://github.com/friedice5467/gacha-daily-mcp.git
cd gacha-daily-mcp
docker compose up --build
```

Open `http://localhost:8420`. The database is created automatically.

The container connects to BlueStacks on the host via `host.docker.internal:5555`. You can change the ADB host/port through the API (`PUT /api/config/adb`).

### Local

```bash
git clone https://github.com/friedice5467/gacha-daily-mcp.git
cd gacha-daily-mcp
uv sync --dev
uv run python -m src.server.main
```

### First run

1. Open the dashboard at `http://localhost:8420`
2. **Games** — Add your game with its Android package name and a vision system prompt (tell the vision LLM what game this is, what the menus look like, etc.)
3. **LLM Config** — Set up the vision and action LLMs. Vision can be a cheap local model. Action benefits from better tool-calling ability.
4. **Tasks** — Build a task with steps. Each step defines what to look for and what to do.
5. **Status** — Run the task.

## Architecture

```
Screenshot -> Vision LLM -> Scene JSON -> Rule Engine -> Action LLM -> ADB
                                              |
                                         (conditions)
                                         match: next / execute / goto / loop / complete
                                         fail:  retry / skip / abort / execute / complete
```

### Task definition example

```json
{
  "name": "Arknights auto-farm",
  "game_package": "com.YoStarEN.Arknights",
  "steps": [
    {
      "name": "Wait for main menu",
      "vision_prompt": "Is this the main menu? Look for the Terminal button.",
      "conditions": [{"field": "screen", "op": "eq", "value": "main_menu"}],
      "on_match": "next",
      "on_fail": "retry",
      "max_retries": 10,
      "timeout_seconds": 60
    },
    {
      "name": "Check stamina",
      "vision_prompt": "Read the current stamina value.",
      "conditions": [{"field": "state.stamina_current", "op": "gte", "value": 30}],
      "on_match": "next",
      "on_fail": "complete"
    },
    {
      "name": "Start quest",
      "vision_prompt": "Is there a quest ready to start?",
      "conditions": [{"field": "state.quest_available", "op": "eq", "value": true}],
      "on_match": {"action": "execute", "goal": "Start the highest available quest with auto-battle"},
      "on_fail": "complete"
    }
  ]
}
```

Conditions support: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `contains`, `exists`. Dot-path field access (`state.stamina_current`). AND by default, wrap in `{"any": [...]}` for OR.

## Project structure

```
src/
  server/      # MCP server, database, entrypoint
  adb/         # ADB client, coordinate normalization, device discovery
  llm/         # LLM adapters (Claude, OpenAI-compatible), tool parser, factory
  tools/       # MCP tool definitions (tap, swipe, screenshot, memory, etc.)
  engine/      # Vision pipeline, rule evaluator, action executor, task loop, scheduler
  safety/      # Rate limiter, guards, emergency stop
  dashboard/   # FastAPI routes + vanilla HTML/JS dashboard
tests/         # 92 tests
```

## Tech stack

Python 3.12, asyncio, MCP SDK, adbutils, Pillow, anthropic, openai, httpx, aiosqlite, FastAPI, APScheduler, structlog, pydantic.

## Running tests

```bash
uv run pytest
```

## License

MIT
