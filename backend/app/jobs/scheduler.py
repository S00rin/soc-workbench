"""APScheduler wiring for backups and intelligence collection."""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..database import SessionLocal
from ..logging_config import get_logger
from ..services import intelligence_automation
from ..services import jobs as job_service
from ..services.backup import create_backup
from ..services.integration_history import enforce_retention
from ..services.settings_service import get_value
from ..models.atlassian import IntegrationHistory

logger = get_logger(__name__)
_scheduler: BackgroundScheduler | None = None


def _daily_backup() -> None:
    job_service.submit("backup", "Scheduled database backup", lambda: str(create_backup()))


def _collect_intelligence() -> None:
    def worker():
        db = SessionLocal()
        try:
            return intelligence_automation.run_all(db)
        finally:
            db.close()
    job_service.submit("intelligence", "Scheduled intel, KB, and IoC refresh", worker)


def _enforce_atlassian_retention() -> None:
    """Apply each tenant's admin-configured integration history retention."""
    db = SessionLocal()
    try:
        days = max(1, int(get_value(db, "atlassian_history_retention_days", "90") or "90"))
        tenant_ids = [value for (value,) in db.query(IntegrationHistory.tenant_id).distinct().all()]
        removed = sum(enforce_retention(db, tenant_id, days) for tenant_id in tenant_ids)
        logger.info("Atlassian retention removed %d history record(s)", removed)
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _daily_backup, CronTrigger(hour=2, minute=0), id="daily_backup",
        replace_existing=True, coalesce=True, max_instances=1,
    )
    _scheduler.add_job(
        _collect_intelligence, IntervalTrigger(minutes=15), id="intelligence_refresh",
        replace_existing=True, coalesce=True, max_instances=1,
    )
    _scheduler.add_job(
        _enforce_atlassian_retention, CronTrigger(hour=3, minute=0), id="atlassian_history_retention",
        replace_existing=True, coalesce=True, max_instances=1,
    )
    _scheduler.start()
    logger.info("Scheduler started with %d job(s)", len(_scheduler.get_jobs()))
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
