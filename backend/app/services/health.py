"""Platform health, Kubernetes-style readiness, and Prometheus text metrics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.automation import IntelSource, IoCSource
from ..models.content import IntelItem
from ..models.core import Job
from ..models.entities import IoC, Notification
from ..models.ops import AnomalyEvent
from . import dashboard_metrics
from .settings_service import get_value

APP_VERSION = "0.5.0"


def _ok(detail: str = "") -> dict:
    return {"ok": True, "detail": detail}


def _fail(detail: str) -> dict:
    return {"ok": False, "detail": detail}


def readiness(db: Session) -> dict:
    """Liveness is `/api/health`; this checks SQLite and the data directory."""
    checks: dict[str, dict] = {}
    settings = get_settings()

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = _ok()
    except Exception as exc:  # noqa: BLE001
        checks["database"] = _fail(str(exc)[:200])

    try:
        settings.ensure_dirs()
        probe = settings.data_dir / ".ready"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        checks["disk"] = _ok(str(settings.data_dir))
    except OSError as exc:
        checks["disk"] = _fail(str(exc)[:200])

    from ..jobs.scheduler import is_running

    running = is_running()
    checks["scheduler"] = {
        "ok": True,
        "running": running,
        "detail": "running" if running else "idle (optional in tests and one-shot jobs)",
    }

    required = checks["database"]["ok"] and checks["disk"]["ok"]
    return {
        "status": "ready" if required else "not_ready",
        "app": settings.app_name,
        "version": APP_VERSION,
        "checks": checks,
    }


def _gauge(name: str, value: float | int, help_text: str, labels: dict[str, str] | None = None) -> list[str]:
    label = ""
    if labels:
        inner = ",".join(f'{key}="{str(val).replace(chr(34), chr(92)+chr(34))}"' for key, val in labels.items())
        label = "{" + inner + "}"
    return [
        f"# HELP {name} {help_text}",
        f"# TYPE {name} gauge",
        f"{name}{label} {value}",
    ]


def prometheus_text(db: Session, *, now: datetime | None = None) -> str:
    """Cheap counters for existing monitoring stacks. No extra dependency."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    last_24h = current - timedelta(hours=24)
    lines: list[str] = []
    lines.extend(_gauge("soc_workbench_up", 1, "SOC Workbench process is serving /metrics"))

    ioc_total = db.query(func.count()).select_from(IoC).scalar() or 0
    ioc_high = db.query(func.count()).select_from(IoC).filter(
        IoC.severity.in_(dashboard_metrics.HIGH_SEVERITIES), IoC.false_positive.is_(False),
        IoC.status.notin_(["expired", "retired"]),
    ).scalar() or 0
    ioc_watchlist = db.query(func.count()).select_from(IoC).filter(IoC.watchlist.is_(True), IoC.false_positive.is_(False)).scalar() or 0
    ioc_expired = db.query(func.count()).select_from(IoC).filter(IoC.status == "expired").scalar() or 0
    lines.extend(_gauge("soc_workbench_iocs", ioc_total, "IoCs stored", {"state": "total"}))
    lines.extend(_gauge("soc_workbench_iocs", ioc_high, "IoCs stored", {"state": "high_open"}))
    lines.extend(_gauge("soc_workbench_iocs", ioc_watchlist, "IoCs stored", {"state": "watchlist"}))
    lines.extend(_gauge("soc_workbench_iocs", ioc_expired, "IoCs stored", {"state": "expired"}))

    jobs_failed = db.query(func.count()).select_from(Job).filter(Job.status == "failed", Job.created_at >= last_24h).scalar() or 0
    jobs_running = db.query(func.count()).select_from(Job).filter(Job.status.in_(["running", "pending"])).scalar() or 0
    lines.extend(_gauge("soc_workbench_jobs", jobs_failed, "Background jobs", {"state": "failed_24h"}))
    lines.extend(_gauge("soc_workbench_jobs", jobs_running, "Background jobs", {"state": "queued"}))

    open_anomalies = db.query(func.count()).select_from(AnomalyEvent).filter(AnomalyEvent.status == "open").scalar() or 0
    silent = db.query(func.count()).select_from(AnomalyEvent).filter(
        AnomalyEvent.status == "open", AnomalyEvent.kind == "silent_sensor").scalar() or 0
    feed = db.query(func.count()).select_from(AnomalyEvent).filter(
        AnomalyEvent.status == "open", AnomalyEvent.kind == "feed_anomaly").scalar() or 0
    lines.extend(_gauge("soc_workbench_anomalies_open", open_anomalies, "Open silent-sensor and feed-anomaly alerts"))
    lines.extend(_gauge("soc_workbench_anomalies_open", silent, "Open silent-sensor and feed-anomaly alerts", {"kind": "silent_sensor"}))
    lines.extend(_gauge("soc_workbench_anomalies_open", feed, "Open silent-sensor and feed-anomaly alerts", {"kind": "feed_anomaly"}))

    failing_intel = db.query(func.count()).select_from(IntelSource).filter(
        IntelSource.enabled.is_(True), IntelSource.failure_count > 0).scalar() or 0
    failing_ioc = db.query(func.count()).select_from(IoCSource).filter(
        IoCSource.enabled.is_(True), IoCSource.failure_count > 0).scalar() or 0
    lines.extend(_gauge("soc_workbench_intel_sources_failing", failing_intel + failing_ioc, "Enabled intel/IoC sources with a failure count"))
    lines.extend(_gauge(
        "soc_workbench_intel_items_24h",
        db.query(func.count()).select_from(IntelItem).filter(IntelItem.created_at >= last_24h).scalar() or 0,
        "Intelligence items ingested in the last 24 hours",
    ))

    notify_failed = db.query(func.count()).select_from(Notification).filter(
        Notification.status == "failed", Notification.created_at >= last_24h).scalar() or 0
    lines.extend(_gauge("soc_workbench_notifications_failed_24h", notify_failed, "Notification deliveries that failed in 24h"))

    backup = dashboard_metrics._last_backup()
    age_hours = -1.0
    if backup["last_backup_at"]:
        parsed = dashboard_metrics._parse_ts(backup["last_backup_at"])
        if parsed:
            age_hours = round((current - parsed).total_seconds() / 3600, 2)
    lines.extend(_gauge("soc_workbench_backup_age_hours", age_hours, "Hours since the last database backup; -1 if none"))
    lines.extend(_gauge("soc_workbench_info", 1, "Build metadata", {
        "app": get_settings().app_name.replace('"', ""),
        "version": APP_VERSION,
        "environment": get_value(db, "environment", get_settings().environment),
    }))
    return "\n".join(lines) + "\n"
