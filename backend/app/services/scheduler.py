"""Periodic synchronisation using APScheduler (in-process, single instance)."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db.session import SessionLocal
from app.services import sync
from app.services.settings_store import SYNC_INTERVALS, load_controller_settings

log = logging.getLogger(__name__)

JOB_ID = "omada-sync"
_scheduler: AsyncIOScheduler | None = None


async def _job() -> None:
    if sync.is_running():
        log.info("Skipping scheduled synchronisation – another one is running")
        return
    try:
        await sync.run_sync("scheduled")
    except sync.SyncError as exc:
        log.info("Scheduled synchronisation skipped: %s", exc)
    except Exception:  # noqa: BLE001
        log.exception("Scheduled synchronisation crashed")


def start() -> None:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
        _scheduler.start()
    reschedule()


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def reschedule() -> None:
    if _scheduler is None:
        return
    with SessionLocal() as db:
        interval = load_controller_settings(db).sync_interval
    seconds = SYNC_INTERVALS.get(interval)
    if _scheduler.get_job(JOB_ID):
        _scheduler.remove_job(JOB_ID)
    if seconds:
        _scheduler.add_job(_job, IntervalTrigger(seconds=seconds), id=JOB_ID, max_instances=1, coalesce=True,
                           misfire_grace_time=60)
        log.info("Automatic synchronisation scheduled every %s", interval)
    else:
        log.info("Automatic synchronisation disabled (manual mode)")


def next_run() -> str | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job(JOB_ID)
    return job.next_run_time.isoformat() if job and job.next_run_time else None
