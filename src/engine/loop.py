from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from src.adb.client import ADBClient
from src.engine.executor import execute_goal
from src.engine.rules import evaluate
from src.engine.vision import SceneState, TaskStep, analyze_screen
from src.llm.base import LLMAdapter
from src.safety.emergency import EmergencyStop
from src.safety.guards import CurrencyGuard, UnknownScreenGuard
from src.safety.rate_limiter import RateLimiter
from src.server.database import get_database
from src.tools import ACTION_TOOLS

log = structlog.get_logger()


class TaskRunError(Exception):
    pass


@dataclass
class TaskRunResult:
    task_id: str
    success: bool
    steps_completed: int = 0
    total_actions: int = 0
    error: str | None = None
    duration_seconds: float = 0.0


@dataclass
class LoadedTask:
    id: str
    name: str
    game_package: str
    steps: list[TaskStep]
    game_context: str = ""


async def load_task(task_id: str) -> LoadedTask:
    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task_row = await cursor.fetchone()
        if task_row is None:
            raise TaskRunError(f"Task not found: {task_id}")

        cursor = await conn.execute(
            "SELECT * FROM task_steps WHERE task_id = ? ORDER BY sort_order", (task_id,)
        )
        step_rows = await cursor.fetchall()
        if not step_rows:
            raise TaskRunError(f"Task has no steps: {task_id}")

        cursor = await conn.execute(
            "SELECT vision_system_prompt FROM games WHERE package_name = ?",
            (task_row["game_package"],),
        )
        game_row = await cursor.fetchone()

    steps = []
    for row in step_rows:
        steps.append(TaskStep(
            name=row["name"],
            vision_prompt=row["vision_prompt"],
            conditions=json.loads(row["conditions"]),
            on_match=json.loads(row["on_match"]) if row["on_match"].startswith("{") else row["on_match"],
            on_fail=json.loads(row["on_fail"]) if row["on_fail"].startswith("{") else row["on_fail"],
            max_retries=row["max_retries"],
            timeout_seconds=row["timeout_seconds"],
        ))

    game_context = ""
    if game_row and game_row["vision_system_prompt"]:
        game_context = game_row["vision_system_prompt"]

    return LoadedTask(
        id=task_row["id"],
        name=task_row["name"],
        game_package=task_row["game_package"],
        steps=steps,
        game_context=game_context,
    )


async def run_task(
    task_id: str,
    adb_client: ADBClient,
    vision_adapter: LLMAdapter,
    action_adapter: LLMAdapter,
    rate_limiter: RateLimiter,
    emergency_stop: EmergencyStop,
    currency_guard: CurrencyGuard,
    unknown_guard: UnknownScreenGuard,
    tool_handler: Any,
) -> TaskRunResult:
    start = time.monotonic()
    task = await load_task(task_id)
    log.info("loop.start", task=task.name, steps=len(task.steps))

    current_app = await adb_client.current_app()
    if current_app != task.game_package:
        await adb_client.launch_app(task.game_package)
        await adb_client.wait_idle()

    step_idx = 0
    steps_completed = 0
    total_actions = 0

    while step_idx < len(task.steps):
        await emergency_stop.check()
        step = task.steps[step_idx]
        log.info("loop.step", step=step.name, index=step_idx)

        retries = 0
        step_start = time.monotonic()
        matched = False

        while retries <= step.max_retries:
            await emergency_stop.check()

            if time.monotonic() - step_start > step.timeout_seconds:
                log.warning("loop.step_timeout", step=step.name)
                break

            screenshot = await adb_client.screenshot()
            scene = await analyze_screen(screenshot, step, vision_adapter, game_context=task.game_context)
            scene_dict = scene.model_dump()

            if evaluate(scene_dict, step.conditions):
                matched = True
                result = await _handle_action(
                    step.on_match, step, scene_dict, task, action_adapter,
                    tool_handler, rate_limiter, emergency_stop,
                    currency_guard, unknown_guard, screenshot,
                )
                total_actions += result.get("actions", 0)

                next_idx = result.get("next_step_idx")
                if result.get("complete"):
                    steps_completed += 1
                    elapsed = time.monotonic() - start
                    await _log_run(task_id, step.name, "complete", None)
                    return TaskRunResult(
                        task_id=task_id, success=True,
                        steps_completed=steps_completed,
                        total_actions=total_actions,
                        duration_seconds=elapsed,
                    )
                if result.get("loop"):
                    await _log_run(task_id, step.name, "loop", None)
                    continue
                if next_idx is not None:
                    step_idx = next_idx
                else:
                    step_idx += 1
                steps_completed += 1
                await _log_run(task_id, step.name, "matched", None)
                break
            else:
                fail_result = await _handle_fail_action(
                    step.on_fail, step, scene_dict, task, action_adapter,
                    tool_handler, rate_limiter, emergency_stop,
                    currency_guard, unknown_guard, screenshot,
                )
                total_actions += fail_result.get("actions", 0)

                if fail_result.get("complete"):
                    elapsed = time.monotonic() - start
                    await _log_run(task_id, step.name, "complete", "on_fail complete")
                    return TaskRunResult(
                        task_id=task_id, success=True,
                        steps_completed=steps_completed,
                        total_actions=total_actions,
                        duration_seconds=elapsed,
                    )
                if fail_result.get("skip"):
                    step_idx += 1
                    await _log_run(task_id, step.name, "skipped", None)
                    break
                if fail_result.get("abort"):
                    elapsed = time.monotonic() - start
                    await _log_run(task_id, step.name, "aborted", None)
                    return TaskRunResult(
                        task_id=task_id, success=False,
                        steps_completed=steps_completed,
                        total_actions=total_actions,
                        error=f"Aborted at step: {step.name}",
                        duration_seconds=elapsed,
                    )

                retries += 1
                await _log_run(task_id, step.name, "retry", f"attempt {retries}")
                cooldown = min(2.0 * retries, 10.0)
                await asyncio.sleep(cooldown)

        if not matched and retries > step.max_retries:
            elapsed = time.monotonic() - start
            await _log_run(task_id, step.name, "failed", "retries exhausted")
            return TaskRunResult(
                task_id=task_id, success=False,
                steps_completed=steps_completed,
                total_actions=total_actions,
                error=f"Retries exhausted at step: {step.name}",
                duration_seconds=elapsed,
            )

    elapsed = time.monotonic() - start
    return TaskRunResult(
        task_id=task_id, success=True,
        steps_completed=steps_completed,
        total_actions=total_actions,
        duration_seconds=elapsed,
    )


async def _handle_action(
    action: str | dict,
    step: TaskStep,
    scene_dict: dict,
    task: LoadedTask,
    action_adapter: LLMAdapter,
    tool_handler: Any,
    rate_limiter: RateLimiter,
    emergency_stop: EmergencyStop,
    currency_guard: CurrencyGuard,
    unknown_guard: UnknownScreenGuard,
    screenshot: bytes | None = None,
) -> dict[str, Any]:
    if action == "next":
        return {}
    if action == "loop":
        return {"loop": True}
    if action == "complete":
        return {"complete": True}
    if isinstance(action, dict):
        if action.get("action") == "execute":
            result = await execute_goal(
                goal=action["goal"],
                scene=scene_dict,
                tools=ACTION_TOOLS,
                adapter=action_adapter,
                tool_handler=tool_handler,
                rate_limiter=rate_limiter,
                emergency_stop=emergency_stop,
                currency_guard=currency_guard,
                unknown_guard=unknown_guard,
                screenshot=screenshot,
            )
            return {"actions": result.actions_taken}
        if action.get("action") == "goto":
            target = action["step"]
            for i, s in enumerate(task.steps):
                if s.name == target:
                    return {"next_step_idx": i}
            raise TaskRunError(f"Goto target not found: {target}")
    return {}


async def _handle_fail_action(
    action: str | dict,
    step: TaskStep,
    scene_dict: dict,
    task: LoadedTask,
    action_adapter: LLMAdapter,
    tool_handler: Any,
    rate_limiter: RateLimiter,
    emergency_stop: EmergencyStop,
    currency_guard: CurrencyGuard,
    unknown_guard: UnknownScreenGuard,
    screenshot: bytes | None = None,
) -> dict[str, Any]:
    if action == "retry":
        return {}
    if action == "skip":
        return {"skip": True}
    if action == "abort":
        return {"abort": True}
    if action == "complete":
        return {"complete": True}
    if isinstance(action, dict) and action.get("action") == "execute":
        result = await execute_goal(
            goal=action["goal"],
            scene=scene_dict,
            tools=ACTION_TOOLS,
            adapter=action_adapter,
            tool_handler=tool_handler,
            rate_limiter=rate_limiter,
            emergency_stop=emergency_stop,
            currency_guard=currency_guard,
            unknown_guard=unknown_guard,
            screenshot=screenshot,
        )
        return {"actions": result.actions_taken}
    return {}


async def _log_run(task_id: str, step_name: str, action: str, details: str | None) -> None:
    try:
        db = get_database()
        async with db.get_db() as conn:
            await conn.execute(
                "INSERT INTO run_log (task_id, step_name, action, details) VALUES (?, ?, ?, ?)",
                (task_id, step_name, action, details),
            )
            await conn.commit()
    except Exception:
        log.warning("loop.log_failed", task_id=task_id, step=step_name)
