"""Lightweight scheduler (Module 14) built on APScheduler.

Registers a small set of maintenance jobs. Job definitions are intentionally
simple; users can extend via the Scheduler settings UI in a later iteration.
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..logging_config import get_logger
from ..services import jobs as job_service
from ..services.backup import create_backup

logger = get_logger(__name__)
_scheduler: BackgroundScheduler | None = None


def _daily_backup() -> None:
    job_service.submit("backup", "Scheduled database backup", lambda: str(create_backup()))


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    # Daily backup at 02:00 UTC.
    _scheduler.add_job(
        _daily_backup,
        CronTrigger(hour=2, minute=0),
        id="daily_backup",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started with %d job(s)", len(_scheduler.get_jobs()))
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
