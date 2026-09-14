"""APScheduler wiring for backups and intelligence collection."""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..database import SessionLocal
from ..logging_config import get_logger
from ..config import get_settings
from ..services import anomaly_detection, executive_brief, intelligence_automation, ioc_lifecycle
from ..services import jobs as job_service
from ..services.backup import create_backup
from ..services.integration_history import enforce_retention
from ..services.settings_service import get_int, get_value
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


def _tenant_ids(db) -> list[str]:
    ids = {get_settings().default_tenant_id}
    from ..models.governance import UserAccount
    from ..models.sensors import Sensor

    ids.update(value for (value,) in db.query(UserAccount.tenant_id).distinct().all() if value)
    ids.update(value for (value,) in db.query(Sensor.tenant_id).distinct().all() if value)
    return sorted(ids)


def _detect_anomalies() -> None:
    def worker():
        db = SessionLocal()
        try:
            results = [anomaly_detection.run_detection(db, tenant_id) for tenant_id in _tenant_ids(db)]
            opened = sum(item.get("opened", 0) for item in results if isinstance(item, dict))
            return f"anomaly detection opened {opened} alert(s)"
        finally:
            db.close()
    job_service.submit("anomaly", "Silent-sensor and feed-anomaly detection", worker)


def _ioc_lifecycle() -> None:
    def worker():
        db = SessionLocal()
        try:
            result = ioc_lifecycle.run_lifecycle(db)
            scores = result.get("scores") or {}
            return f"IoC lifecycle: {scores}"
        finally:
            db.close()
    job_service.submit("ioc_lifecycle", "IoC decay, expiry and optional retro-hunt", worker)


def _executive_brief() -> None:
    def worker():
        db = SessionLocal()
        try:
            result = executive_brief.scheduled_run(db)
            if result.get("skipped"):
                return f"executive brief skipped ({result.get('reason')})"
            return f"executive brief report #{result.get('report_id')}"
        finally:
            db.close()
    job_service.submit("executive_brief", "Scheduled executive brief (PDF + Confluence)", worker)


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
    db = SessionLocal()
    try:
        anomaly_minutes = max(5, get_int(db, "anomaly_interval_minutes", 15))
        brief_hour = min(23, max(0, get_int(db, "brief_hour_utc", 6)))
    finally:
        db.close()
    _scheduler.add_job(
        _detect_anomalies, IntervalTrigger(minutes=anomaly_minutes), id="anomaly_detection",
        replace_existing=True, coalesce=True, max_instances=1,
    )
    _scheduler.add_job(
        _ioc_lifecycle, CronTrigger(hour=4, minute=30), id="ioc_lifecycle",
        replace_existing=True, coalesce=True, max_instances=1,
    )
    _scheduler.add_job(
        _executive_brief, CronTrigger(hour=brief_hour, minute=0), id="executive_brief",
        replace_existing=True, coalesce=True, max_instances=1,
    )
    _scheduler.start()
    logger.info("Scheduler started with %d job(s)", len(_scheduler.get_jobs()))
    return _scheduler


def is_running() -> bool:
    return bool(_scheduler and _scheduler.running)


def describe_jobs() -> list[dict]:
    """Scheduled jobs and their next fire time; empty when the scheduler is idle."""
    if not _scheduler or not _scheduler.running:
        return []
    return [
        {"id": job.id, "name": job.name, "trigger": str(job.trigger),
         "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None}
        for job in _scheduler.get_jobs()
    ]


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
