from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.server.database import get_database

log = structlog.get_logger()

_scheduler: AsyncIOScheduler | None = None


async def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler()

    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute(
            "SELECT s.*, t.name as task_name FROM schedules s JOIN tasks t ON s.task_id = t.id WHERE s.enabled = 1"
        )
        rows = await cursor.fetchall()

    for row in rows:
        _add_job(_scheduler, row["id"], row["task_id"], row["cron"], row["task_name"])

    _scheduler.start()
    log.info("scheduler.started", jobs=len(_scheduler.get_jobs()))
    return _scheduler


def _add_job(scheduler: AsyncIOScheduler, schedule_id: str, task_id: str, cron: str, task_name: str) -> None:
    try:
        trigger = CronTrigger.from_crontab(cron)
    except ValueError:
        log.warning("scheduler.invalid_cron", schedule_id=schedule_id, cron=cron)
        return

    scheduler.add_job(
        _run_scheduled_task,
        trigger=trigger,
        id=schedule_id,
        args=[task_id, schedule_id],
        name=f"task:{task_name}",
        replace_existing=True,
    )
    log.info("scheduler.job_added", schedule_id=schedule_id, task=task_name, cron=cron)


async def _run_scheduled_task(task_id: str, schedule_id: str) -> None:
    from src.server.main import _start_task_run

    log.info("scheduler.triggering", task_id=task_id, schedule_id=schedule_id)

    db = get_database()
    async with db.get_db() as conn:
        await conn.execute(
            "UPDATE schedules SET last_run = datetime('now') WHERE id = ?",
            (schedule_id,),
        )
        await conn.commit()

    await _start_task_run(task_id)


async def reload_schedules() -> None:
    if _scheduler is None:
        return

    _scheduler.remove_all_jobs()

    db = get_database()
    async with db.get_db() as conn:
        cursor = await conn.execute(
            "SELECT s.*, t.name as task_name FROM schedules s JOIN tasks t ON s.task_id = t.id WHERE s.enabled = 1"
        )
        rows = await cursor.fetchall()

    for row in rows:
        _add_job(_scheduler, row["id"], row["task_id"], row["cron"], row["task_name"])

    log.info("scheduler.reloaded", jobs=len(_scheduler.get_jobs()))


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("scheduler.stopped")
