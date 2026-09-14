"""Executive and technical dashboard aggregations.

Both views are computed on demand from the local SQLite store. Everything is
deterministic and explainable: the posture score lists every component, its
weight and the raw observation behind it, so a manager can trace a number back
to the data that produced it. Metrics that cannot be computed (no sensors, no
integrations, ...) are reported as ``None`` and excluded from the score rather
than silently counted as zero.
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.atlassian import AtlassianConnection, IntegrationHistory
from ..models.automation import IntelSource, IoCObservation, IoCSource
from ..models.content import Document, IntelItem, KnowledgeItem
from ..models.core import Job, SensitivePattern, TokenMapping
from ..models.entities import Analysis, IoC, Notification, Project, Report
from ..models.governance import (
    ExternalConnection, FeaturePolicy, IntegrationChatTurn, UserAccount, UserActivity,
)
from ..models.ops import AnomalyEvent
from ..models.sensors import Sensor, SensorDocument, SensorLogSource
from ..security import AuthContext
from .access_control import policy_state
from .sensors import MITRE_TACTICS

HIGH_SEVERITIES = {"high", "critical"}
POSTURE_WEIGHTS = {
    "detection_coverage": 0.20,
    "integration_readiness": 0.15,
    "automation_reliability": 0.15,
    "intel_freshness": 0.15,
    "portfolio_health": 0.15,
    "ioc_hygiene": 0.10,
    "governance": 0.10,
}


# --- helpers ----------------------------------------------------------------

def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _parse_ts(value: Any) -> datetime | None:
    """Parse the free-form string timestamps used by IoCs and intel sources."""
    if isinstance(value, datetime):
        return _aware(value)
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return _aware(datetime.fromisoformat(normalized))
    except ValueError:
        try:
            return datetime.strptime(normalized[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def _iso(value: datetime | None) -> str | None:
    value = _aware(value)
    return value.isoformat() if value else None


def _pct(numerator: float, denominator: float) -> float | None:
    if not denominator:
        return None
    return round(numerator / denominator * 100, 1)


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return round(ordered[index], 1)


def _compare(current: int | float, previous: int | float) -> dict[str, Any]:
    delta = current - previous
    return {
        "value": current,
        "previous": previous,
        "delta": delta,
        "delta_pct": round(delta / previous * 100, 1) if previous else None,
    }


def _daily_buckets(values: Iterable[datetime | None], start_day: date, days: int) -> list[dict[str, Any]]:
    counts: Counter[date] = Counter()
    for value in values:
        parsed = _aware(value)
        if parsed is not None:
            counts[parsed.date()] += 1
    return [
        {"date": (start_day + timedelta(days=offset)).isoformat(),
         "count": counts.get(start_day + timedelta(days=offset), 0)}
        for offset in range(days)
    ]


def _series(db: Session, column, start: datetime, start_day: date, days: int, *filters) -> list[dict[str, Any]]:
    rows = db.query(column).filter(column >= start, *filters).all()
    return _daily_buckets((row[0] for row in rows), start_day, days)


def _count_between(db: Session, column, start: datetime, end: datetime | None = None, *filters) -> int:
    query = db.query(func.count()).select_from(column.class_).filter(column >= start, *filters)
    if end is not None:
        query = query.filter(column < end)
    return int(query.scalar() or 0)


def _grouped(rows: Iterable[tuple[Any, int]]) -> dict[str, int]:
    return {str(key or "unknown"): int(count) for key, count in rows}


def _dir_size(path: Path) -> int:
    total = 0
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False):
                        total += _dir_size(Path(entry.path))
                except OSError:
                    continue
    except OSError:
        return 0
    return total


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _connector_status(row: AtlassianConnection | ExternalConnection) -> str:
    if not row.enabled:
        return "disabled"
    if row.last_error_code:
        return "error"
    if row.last_success_at:
        return "connected"
    return "untested"


def _risk_entries(project: Project) -> list[dict[str, Any]]:
    """Project risks are free-form JSON; normalize strings and dicts."""
    entries = []
    for item in project.risks or []:
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("risk") or item.get("description") or item.get("name") or "").strip()
            severity = str(item.get("severity") or item.get("level") or item.get("impact") or "").strip().lower()
            status = str(item.get("status") or "").strip().lower()
        else:
            title, severity, status = str(item).strip(), "", ""
        if not title or status in {"closed", "resolved", "done"}:
            continue
        entries.append({
            "project_id": project.id, "project": project.name, "customer": project.customer,
            "risk": title[:200], "severity": severity or "unrated", "health": project.health,
        })
    return entries


_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unrated": 4}


# --- shared building blocks ---------------------------------------------------

def _window(days: int, now: datetime | None) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    since = current - timedelta(days=days)
    return {
        "now": current,
        "since": since,
        "previous_since": since - timedelta(days=days),
        "trend_start": (current - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0),
        "days": days,
    }


def _connectors(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    rows = [
        *db.query(AtlassianConnection).filter(AtlassianConnection.tenant_id == tenant_id).all(),
        *db.query(ExternalConnection).filter(ExternalConnection.tenant_id == tenant_id).all(),
    ]
    return [
        {
            "id": row.id, "name": row.name,
            "provider": "atlassian" if isinstance(row, AtlassianConnection) else row.provider,
            "products": list(row.products or []) if isinstance(row, AtlassianConnection) else [row.provider],
            "enabled": row.enabled, "status": _connector_status(row),
            "last_success_at": _iso(row.last_success_at), "last_test_at": _iso(row.last_test_at),
            "error_code": row.last_error_code or "", "error_summary": (row.last_error_summary or "")[:200],
        }
        for row in rows
    ]


def _intel_sources(db: Session, now: datetime) -> list[dict[str, Any]]:
    items = []
    for kind, model in (("rss", IntelSource), ("ioc", IoCSource)):
        for row in db.query(model).all():
            last_success = _parse_ts(row.last_success_at)
            stale_after = timedelta(minutes=max(15, int(row.interval_minutes or 60)) * 3)
            if not row.enabled:
                status = "disabled"
            elif row.failure_count or row.last_error:
                status = "failing"
            elif last_success is None:
                status = "never_run"
            elif now - last_success > stale_after:
                status = "stale"
            else:
                status = "healthy"
            items.append({
                "id": row.id, "name": row.name, "kind": kind, "enabled": row.enabled,
                "interval_minutes": row.interval_minutes, "trust_score": row.trust_score,
                "failure_count": row.failure_count, "last_success_at": _iso(last_success),
                "last_error": (row.last_error or "")[:200], "status": status,
            })
    return items


def _tactic_coverage(db: Session, tenant_id: str) -> dict[str, Any]:
    sensors = db.query(Sensor).filter(Sensor.tenant_id == tenant_id, Sensor.status == "active").all()
    matrix: dict[str, list[str]] = {tactic: [] for tactic in MITRE_TACTICS}
    for sensor in sensors:
        for tactic in sensor.mitre_tactics or []:
            if tactic in matrix:
                matrix[tactic].append(sensor.name)
    covered = sum(1 for names in matrix.values() if names)
    return {
        "total": len(MITRE_TACTICS), "covered": covered, "coverage_pct": _pct(covered, len(MITRE_TACTICS)),
        "tactics": [{"tactic": tactic, "sensors": names, "count": len(names)} for tactic, names in matrix.items()],
        "gaps": [tactic for tactic, names in matrix.items() if not names],
        "active_sensors": len(sensors),
    }


def _job_stats(db: Session, since: datetime) -> dict[str, Any]:
    rows = db.query(Job).filter(Job.created_at >= since).all()
    by_kind: dict[str, Counter] = defaultdict(Counter)
    durations: list[float] = []
    for job in rows:
        by_kind[job.kind][job.status] += 1
        started, finished = _aware(job.started_at), _aware(job.finished_at)
        if started and finished and finished >= started:
            durations.append((finished - started).total_seconds())
    finished_count = sum(1 for job in rows if job.status in {"completed", "failed"})
    completed = sum(1 for job in rows if job.status == "completed")
    return {
        "total": len(rows),
        "completed": completed,
        "failed": finished_count - completed,
        "success_rate": _pct(completed, finished_count),
        "avg_duration_s": round(mean(durations), 1) if durations else None,
        "p95_duration_s": _percentile(durations, 95),
        "by_kind": {kind: dict(counter) for kind, counter in sorted(by_kind.items())},
    }


def _feature_expiry(db: Session, tenant_id: str, now: datetime) -> list[dict[str, Any]]:
    items = []
    for row in db.query(FeaturePolicy).filter(FeaturePolicy.tenant_id == tenant_id).all():
        state = policy_state(row, now=now)
        expires = _aware(row.expires_at)
        if state["active"] and expires and now < expires <= now + timedelta(days=30):
            items.append({"key": row.feature_key, "expires_at": expires.isoformat(),
                          "days_left": max(0, (expires - now).days)})
    return sorted(items, key=lambda item: item["days_left"])


def _last_backup() -> dict[str, Any]:
    settings = get_settings()
    try:
        backups = sorted(
            (path for path in settings.backups_dir.glob("*.zip") if path.is_file()),
            key=lambda path: path.stat().st_mtime, reverse=True,
        )
    except OSError:
        backups = []
    latest = backups[0] if backups else None
    return {
        "count": len(backups),
        "last_backup_at": datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).isoformat() if latest else None,
        "last_backup_bytes": latest.stat().st_size if latest else 0,
    }


# --- executive dashboard -------------------------------------------------------

def executive_summary(db: Session, context: AuthContext, *, days: int = 30, now: datetime | None = None) -> dict[str, Any]:
    window = _window(days, now)
    current, since, previous_since = window["now"], window["since"], window["previous_since"]
    trend_start, trend_days = window["trend_start"], days
    tenant = context.tenant_id

    projects = db.query(Project).filter(Project.status == "active").order_by(Project.updated_at.desc()).all()
    health = Counter((project.health or "green") for project in projects)
    risk_register = sorted(
        (entry for project in projects for entry in _risk_entries(project)),
        key=lambda entry: (_SEVERITY_ORDER.get(entry["severity"], 4), entry["health"] != "red"),
    )[:10]

    def compare(column, *filters) -> dict[str, Any]:
        return _compare(
            _count_between(db, column, since, None, *filters),
            _count_between(db, column, previous_since, since, *filters),
        )

    iocs = compare(IoC.created_at)
    intel = compare(IntelItem.created_at)
    documents = compare(Document.created_at)
    reports = compare(Report.created_at)
    knowledge = compare(KnowledgeItem.created_at)
    high_iocs_open = db.query(func.count()).select_from(IoC).filter(
        IoC.severity.in_(HIGH_SEVERITIES), IoC.false_positive.is_(False),
    ).scalar() or 0
    ioc_total = db.query(func.count()).select_from(IoC).scalar() or 0
    ioc_fp = db.query(func.count()).select_from(IoC).filter(IoC.false_positive.is_(True)).scalar() or 0
    ioc_expired = sum(
        1 for (value,) in db.query(IoC.expires_at).filter(IoC.expires_at != "").all()
        if (parsed := _parse_ts(value)) and parsed < current
    )

    jobs = _job_stats(db, since)
    connectors = _connectors(db, tenant)
    connected = sum(1 for item in connectors if item["status"] == "connected")
    sources = _intel_sources(db, current)
    # Sources that have never run are not evidence of staleness, so they are
    # excluded from the freshness ratio instead of dragging it to zero.
    enabled_sources = [item for item in sources if item["enabled"] and item["status"] != "never_run"]
    healthy_sources = sum(1 for item in enabled_sources if item["status"] == "healthy")
    coverage = _tactic_coverage(db, tenant)
    expiring = _feature_expiry(db, tenant, current)
    backup = _last_backup()

    users_total = db.query(func.count()).select_from(UserAccount).filter(UserAccount.tenant_id == tenant).scalar() or 0
    users_active = db.query(func.count()).select_from(UserAccount).filter(
        UserAccount.tenant_id == tenant, UserAccount.active.is_(True)).scalar() or 0
    active_actors = db.query(func.count(func.distinct(UserActivity.actor_user_id))).filter(
        UserActivity.tenant_id == tenant, UserActivity.created_at >= since).scalar() or 0
    activity = compare(UserActivity.created_at, UserActivity.tenant_id == tenant)

    # Posture score: each component is 0-100 or None (not measurable).
    portfolio_score = None
    if projects:
        portfolio_score = round(mean({"green": 100, "yellow": 50}.get(project.health, 0) for project in projects))
    components = [
        {"key": "detection_coverage", "label": "Detection coverage", "score": coverage["coverage_pct"],
         "detail": f'{coverage["covered"]}/{coverage["total"]} ATT&CK tactics covered by active sensors'},
        {"key": "integration_readiness", "label": "Integration readiness", "score": _pct(connected, len(connectors)),
         "detail": f"{connected}/{len(connectors)} connections healthy"},
        {"key": "automation_reliability", "label": "Automation reliability", "score": jobs["success_rate"],
         "detail": f'{jobs["completed"]}/{jobs["completed"] + jobs["failed"]} background jobs succeeded'},
        {"key": "intel_freshness", "label": "Intelligence freshness", "score": _pct(healthy_sources, len(enabled_sources)),
         "detail": f"{healthy_sources}/{len(enabled_sources)} enabled sources fresh (sources that never ran are excluded)"},
        {"key": "portfolio_health", "label": "Investigation health", "score": portfolio_score,
         "detail": f'{health.get("green", 0)} green · {health.get("yellow", 0)} yellow · {health.get("red", 0)} red'},
        {"key": "ioc_hygiene", "label": "IoC hygiene",
         "score": round(max(0.0, 100 - (ioc_fp + ioc_expired) / ioc_total * 100), 1) if ioc_total else None,
         "detail": f"{ioc_fp} false positives · {ioc_expired} expired of {ioc_total}"},
        {"key": "governance", "label": "Governance", "score": max(0, 100 - 20 * len(expiring)),
         "detail": f"{len(expiring)} feature policies expire within 30 days"},
    ]
    weighted_total = 0.0
    weight_sum = 0.0
    for component in components:
        component["weight"] = POSTURE_WEIGHTS[component["key"]]
        if component["score"] is not None:
            weighted_total += component["score"] * component["weight"]
            weight_sum += component["weight"]
    score = round(weighted_total / weight_sum) if weight_sum else 0

    open_anomalies = db.query(AnomalyEvent).filter(
        AnomalyEvent.tenant_id == tenant, AnomalyEvent.status == "open",
    ).order_by(AnomalyEvent.last_seen.desc()).limit(8).all()
    attention = _attention_items(
        jobs=jobs, connectors=connectors, sources=sources, expiring=expiring, health=health,
        coverage=coverage, backup=backup, now=current, high_iocs_open=high_iocs_open,
        anomalies=open_anomalies,
    )

    return {
        "generated_at": current.isoformat(),
        "period": {"days": days, "since": since.isoformat(), "until": current.isoformat()},
        "posture": {"score": score, "grade": _grade(score), "components": components},
        "kpis": {
            "active_investigations": len(projects),
            "red_investigations": health.get("red", 0),
            "avg_progress": round(mean(project.progress or 0 for project in projects)) if projects else None,
            "iocs_new": iocs,
            "high_severity_iocs_open": high_iocs_open,
            "intel_items": intel,
            "documents_processed": documents,
            "knowledge_added": knowledge,
            "reports_delivered": reports,
            "job_success_rate": jobs["success_rate"],
            "integration_readiness": _pct(connected, len(connectors)),
            "sensor_coverage": coverage["coverage_pct"],
            "users": {"total": users_total, "active": users_active, "engaged": active_actors},
            "activity_events": activity,
        },
        "trends": {
            "iocs": _series(db, IoC.created_at, trend_start, trend_start.date(), trend_days),
            "intel": _series(db, IntelItem.created_at, trend_start, trend_start.date(), trend_days),
            "documents": _series(db, Document.created_at, trend_start, trend_start.date(), trend_days),
            "reports": _series(db, Report.created_at, trend_start, trend_start.date(), trend_days),
            "activity": _series(db, UserActivity.created_at, trend_start, trend_start.date(), trend_days,
                                UserActivity.tenant_id == tenant),
        },
        "portfolio": {
            "health": {"green": health.get("green", 0), "yellow": health.get("yellow", 0), "red": health.get("red", 0)},
            "projects": [
                {"id": project.id, "name": project.name, "customer": project.customer, "health": project.health,
                 "progress": project.progress, "manager": project.manager, "end_date": project.end_date,
                 "risks": len(project.risks or []), "issues": len(project.issues or []),
                 "open_actions": len(project.action_items or [])}
                for project in projects[:8]
            ],
        },
        "risk_register": risk_register,
        "coverage": coverage,
        "integrations": {"total": len(connectors), "connected": connected,
                         "attention": sum(1 for item in connectors if item["status"] in {"error", "disabled"})},
        "feature_expiry": expiring,
        "backup": backup,
        "attention": attention,
    }


def _attention_items(*, jobs, connectors, sources, expiring, health, coverage, backup, now, high_iocs_open, anomalies=None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def add(severity: str, title: str, detail: str, link: str) -> None:
        items.append({"severity": severity, "title": title, "detail": detail, "link": link})

    if anomalies:
        high = sum(1 for row in anomalies if row.severity == "high")
        add(
            "high" if high else "medium",
            f"{len(anomalies)} silent-sensor / feed-anomaly alert(s)",
            ", ".join(row.title for row in anomalies[:4]),
            "/?view=technical",
        )
    if health.get("red"):
        add("high", f'{health["red"]} investigation(s) in red health', "Review blockers with the project owners.", "/data?tab=projects")
    broken = [item for item in connectors if item["status"] == "error"]
    if broken:
        add("high", f"{len(broken)} integration connection(s) failing",
            ", ".join(f'{item["name"]} ({item["error_code"]})' for item in broken[:3]), "/integrations?tab=atlassian")
    if jobs["failed"]:
        add("medium" if jobs["failed"] < 3 else "high", f'{jobs["failed"]} background job(s) failed in period',
            "Open Operations to inspect errors and retry.", "/operations?tab=jobs")
    failing_sources = [item for item in sources if item["status"] in {"failing", "stale"} and item["enabled"]]
    if failing_sources:
        add("medium", f"{len(failing_sources)} intelligence source(s) failing or stale",
            ", ".join(item["name"] for item in failing_sources[:4]), "/intelligence?tab=automation")
    for item in expiring:
        add("high" if item["days_left"] <= 7 else "medium", f'Feature "{item["key"]}" expires in {item["days_left"]} day(s)',
            "Extend the policy window to avoid a service interruption.", "/admin/access")
    if coverage["active_sensors"] and (coverage["coverage_pct"] or 0) < 50:
        add("medium", "ATT&CK tactic coverage below 50%", f'Gaps: {", ".join(coverage["gaps"][:5])}', "/sensors")
    elif not coverage["active_sensors"]:
        add("low", "No active sensors in the library", "Add the equipment your SOC operates to measure detection coverage.", "/sensors")
    last_backup = _parse_ts(backup["last_backup_at"])
    if last_backup is None:
        add("high", "No database backup found", "Run a backup from Operations or wait for the 02:00 UTC schedule.", "/operations?tab=jobs")
    elif now - last_backup > timedelta(hours=48):
        add("medium", "Last backup is older than 48 hours", f"Last backup: {last_backup.isoformat()}", "/operations?tab=jobs")
    if high_iocs_open > 25:
        add("low", f"{high_iocs_open} high/critical IoCs active", "Consider expiring or tagging stale high-severity indicators.", "/data?tab=iocs")
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(items, key=lambda item: order[item["severity"]])


_BRIEF_LABELS = {
    "en": {
        "title": "SOC Executive Brief", "period": "Period", "last": "last", "days": "days",
        "until": "until", "posture": "Security posture", "grade": "grade",
        "kpis": "Headline KPIs", "kpi": "KPI", "value": "Value",
        "investigations": "Active investigations", "red": "red",
        "new_iocs": "New IoCs", "high_iocs": "High/critical IoCs active",
        "intel": "Intelligence items", "documents": "Documents processed",
        "reports": "Reports delivered", "automation": "Automation success rate",
        "integrations": "Integration readiness", "coverage": "ATT&CK tactic coverage",
        "users": "Engaged users", "of": "of", "active": "active",
        "components": "Posture components", "component": "Component",
        "score": "Score", "weight": "Weight", "evidence": "Evidence",
        "attention": "Needs attention", "no_attention": "Nothing requires executive attention in this period.",
        "portfolio": "Investigation portfolio", "project": "Project", "customer": "Customer",
        "health": "Health", "progress": "Progress", "risks": "Risks",
        "no_projects": "No active investigations.", "top_risks": "Top risks",
        "gaps": "Detection gaps", "generated": "Generated by SOC Workbench at",
        "vs": "vs previous period",
    },
    "fa": {
        "title": "خلاصه مدیریتی SOC", "period": "دوره", "last": "آخرین", "days": "روز",
        "until": "تا", "posture": "وضعیت امنیتی", "grade": "رتبه",
        "kpis": "شاخص‌های اصلی", "kpi": "شاخص", "value": "مقدار",
        "investigations": "تحقیقات فعال", "red": "قرمز",
        "new_iocs": "شاخص‌های جدید", "high_iocs": "شاخص‌های شدید/بحرانی فعال",
        "intel": "اقلام اطلاعاتی", "documents": "اسناد پردازش‌شده",
        "reports": "گزارش‌های تحویل‌شده", "automation": "نرخ موفقیت خودکارسازی",
        "integrations": "آمادگی یکپارچه‌سازی", "coverage": "پوشش تاکتیک ATT&CK",
        "users": "کاربران درگیر", "of": "از", "active": "فعال",
        "components": "اجزای وضعیت", "component": "جزء",
        "score": "امتیاز", "weight": "وزن", "evidence": "شواهد",
        "attention": "نیاز به توجه", "no_attention": "در این دوره موردی نیازمند توجه مدیریتی نیست.",
        "portfolio": "سبد تحقیقات", "project": "پروژه", "customer": "مشتری",
        "health": "سلامت", "progress": "پیشرفت", "risks": "ریسک‌ها",
        "no_projects": "تحقیق فعالی وجود ندارد.", "top_risks": "ریسک‌های اصلی",
        "gaps": "شکاف‌های آشکارسازی", "generated": "تولیدشده توسط SOC Workbench در",
        "vs": "نسبت به دوره قبل",
    },
}


def render_executive_brief(summary: dict[str, Any], language: str = "en") -> str:
    """Render a Markdown executive brief from an executive summary payload."""
    kpis = summary["kpis"]
    posture = summary["posture"]
    t = _BRIEF_LABELS.get(language) or _BRIEF_LABELS["en"]

    def trend(metric: dict[str, Any]) -> str:
        delta = metric["delta"]
        arrow = "▲" if delta > 0 else "▼" if delta < 0 else "•"
        pct_delta = f' ({metric["delta_pct"]:+.1f}%)' if metric["delta_pct"] is not None else ""
        return f'{metric["value"]} {arrow} {abs(delta)}{pct_delta} {t["vs"]}'

    def pct(value: float | None) -> str:
        return "N/A" if value is None else f"{value:g}%"

    lines = [
        f'# {t["title"]}', "",
        f'**{t["period"]}:** {t["last"]} {summary["period"]["days"]} {t["days"]} ({t["until"]} {summary["generated_at"][:10]})',
        f'**{t["posture"]}:** {posture["score"]}/100 ({t["grade"]} {posture["grade"]})', "",
        f'## {t["kpis"]}', "",
        f'| {t["kpi"]} | {t["value"]} |', "|---|---|",
        f'| {t["investigations"]} | {kpis["active_investigations"]} ({kpis["red_investigations"]} {t["red"]}) |',
        f'| {t["new_iocs"]} | {trend(kpis["iocs_new"])} |',
        f'| {t["high_iocs"]} | {kpis["high_severity_iocs_open"]} |',
        f'| {t["intel"]} | {trend(kpis["intel_items"])} |',
        f'| {t["documents"]} | {trend(kpis["documents_processed"])} |',
        f'| {t["reports"]} | {trend(kpis["reports_delivered"])} |',
        f'| {t["automation"]} | {pct(kpis["job_success_rate"])} |',
        f'| {t["integrations"]} | {pct(kpis["integration_readiness"])} |',
        f'| {t["coverage"]} | {pct(kpis["sensor_coverage"])} |',
        f'| {t["users"]} | {kpis["users"]["engaged"]} {t["of"]} {kpis["users"]["active"]} {t["active"]} |',
        "", f'## {t["components"]}', "",
        f'| {t["component"]} | {t["score"]} | {t["weight"]} | {t["evidence"]} |', "|---|---|---|---|",
    ]
    for component in posture["components"]:
        score = "N/A" if component["score"] is None else f'{component["score"]:g}'
        lines.append(f'| {component["label"]} | {score} | {component["weight"]:.0%} | {component["detail"]} |')
    lines.extend(["", f'## {t["attention"]}', ""])
    if summary["attention"]:
        lines.extend(f'- **{item["severity"].upper()}** — {item["title"]}: {item["detail"]}' for item in summary["attention"])
    else:
        lines.append(f'- {t["no_attention"]}')
    lines.extend(["", f'## {t["portfolio"]}', ""])
    if summary["portfolio"]["projects"]:
        lines.extend([f'| {t["project"]} | {t["customer"]} | {t["health"]} | {t["progress"]} | {t["risks"]} |', "|---|---|---|---|---|"])
        lines.extend(
            f'| {project["name"]} | {project["customer"] or "—"} | {project["health"]} | {project["progress"]}% | {project["risks"]} |'
            for project in summary["portfolio"]["projects"]
        )
    else:
        lines.append(t["no_projects"])
    if summary["risk_register"]:
        lines.extend(["", f'## {t["top_risks"]}', ""])
        lines.extend(f'- [{entry["severity"]}] {entry["project"]}: {entry["risk"]}' for entry in summary["risk_register"])
    if summary["coverage"]["gaps"]:
        lines.extend(["", f'## {t["gaps"]}', "", ", ".join(summary["coverage"]["gaps"])])
    lines.extend(["", f'_{t["generated"]} {summary["generated_at"]}_'])
    return "\n".join(lines)


# --- technical dashboard -------------------------------------------------------

def technical_summary(db: Session, context: AuthContext, *, days: int = 7, now: datetime | None = None) -> dict[str, Any]:
    window = _window(days, now)
    current, since = window["now"], window["since"]
    tenant = context.tenant_id
    last_24h = current - timedelta(hours=24)

    return {
        "generated_at": current.isoformat(),
        "period": {"days": days, "since": since.isoformat(), "until": current.isoformat()},
        "iocs": _ioc_analytics(db, current, since, last_24h),
        "intel": _intel_analytics(db, current, since, last_24h),
        "jobs": _job_analytics(db, since, last_24h),
        "integrations": _integration_analytics(db, tenant, since),
        "telemetry": _telemetry_analytics(db, tenant),
        "api": _api_analytics(db, context, since, current),
        "storage": _storage_analytics(db),
        "anomalies": _anomaly_analytics(db, tenant),
    }


def _ioc_analytics(db: Session, now: datetime, since: datetime, last_24h: datetime) -> dict[str, Any]:
    total = db.query(func.count()).select_from(IoC).scalar() or 0
    false_positives = db.query(func.count()).select_from(IoC).filter(IoC.false_positive.is_(True)).scalar() or 0
    expiring_30d = expired = 0
    for (value,) in db.query(IoC.expires_at).filter(IoC.expires_at != "").all():
        parsed = _parse_ts(value)
        if parsed is None:
            continue
        if parsed < now:
            expired += 1
        elif parsed <= now + timedelta(days=30):
            expiring_30d += 1
    multi_source = (
        db.query(IoCObservation.ioc_id)
        .group_by(IoCObservation.ioc_id)
        .having(func.count(func.distinct(IoCObservation.source_name)) > 1)
        .count()
    )
    top_sources = db.query(IoC.source, func.count()).filter(IoC.source != "").group_by(IoC.source) \
        .order_by(func.count().desc()).limit(8).all()
    return {
        "total": total,
        "by_type": _grouped(db.query(IoC.ioc_type, func.count()).group_by(IoC.ioc_type).all()),
        "by_severity": _grouped(db.query(IoC.severity, func.count()).group_by(IoC.severity).all()),
        "by_confidence": _grouped(db.query(IoC.confidence, func.count()).group_by(IoC.confidence).all()),
        "false_positives": false_positives,
        "fp_ratio": _pct(false_positives, total),
        "new_24h": _count_between(db, IoC.created_at, last_24h),
        "new_period": _count_between(db, IoC.created_at, since),
        "expiring_30d": expiring_30d,
        "expired": expired,
        "by_status": _grouped(db.query(IoC.status, func.count()).group_by(IoC.status).all()),
        "watchlist": db.query(func.count()).select_from(IoC).filter(IoC.watchlist.is_(True), IoC.false_positive.is_(False)).scalar() or 0,
        "avg_score": round(float(db.query(func.avg(IoC.score)).scalar() or 0), 1) if total else None,
        "multi_source": multi_source,
        "top_sources": [{"name": name, "count": int(count)} for name, count in top_sources],
        "recent_high": [
            {"id": row.id, "value": row.value, "ioc_type": row.ioc_type, "severity": row.severity,
             "source": row.source, "created_at": _iso(row.created_at)}
            for row in db.query(IoC).filter(IoC.severity.in_(HIGH_SEVERITIES), IoC.false_positive.is_(False))
            .order_by(IoC.created_at.desc()).limit(8).all()
        ],
    }


def _intel_analytics(db: Session, now: datetime, since: datetime, last_24h: datetime) -> dict[str, Any]:
    sources = _intel_sources(db, now)
    status_counts = Counter(item["status"] for item in sources)
    relevance = db.query(func.avg(IntelItem.relevance)).filter(IntelItem.created_at >= since).scalar()
    return {
        "items_24h": _count_between(db, IntelItem.created_at, last_24h),
        "items_period": _count_between(db, IntelItem.created_at, since),
        "unread": db.query(func.count()).select_from(IntelItem).filter(IntelItem.read.is_(False)).scalar() or 0,
        "saved": db.query(func.count()).select_from(IntelItem).filter(IntelItem.saved.is_(True)).scalar() or 0,
        "avg_relevance": round(float(relevance), 2) if relevance is not None else None,
        "by_category": _grouped(
            db.query(IntelItem.category, func.count()).filter(IntelItem.created_at >= since)
            .group_by(IntelItem.category).order_by(func.count().desc()).limit(10).all()
        ),
        "by_source": _grouped(
            db.query(IntelItem.source, func.count()).filter(IntelItem.created_at >= since)
            .group_by(IntelItem.source).order_by(func.count().desc()).limit(10).all()
        ),
        "sources": sources,
        "source_status": {key: status_counts.get(key, 0) for key in ("healthy", "stale", "failing", "never_run", "disabled")},
    }


def _anomaly_analytics(db: Session, tenant: str) -> dict[str, Any]:
    from . import anomaly_detection

    return anomaly_detection.summary(db, tenant)


def _job_analytics(db: Session, since: datetime, last_24h: datetime) -> dict[str, Any]:
    from ..jobs.scheduler import describe_jobs

    stats = _job_stats(db, since)
    stats.update({
        "failed_24h": db.query(func.count()).select_from(Job).filter(Job.status == "failed", Job.created_at >= last_24h).scalar() or 0,
        "queue": {
            "pending": db.query(func.count()).select_from(Job).filter(Job.status == "pending").scalar() or 0,
            "running": db.query(func.count()).select_from(Job).filter(Job.status == "running").scalar() or 0,
        },
        "scheduler": describe_jobs(),
        "recent_failures": [
            {"id": job.id, "name": job.name, "kind": job.kind, "error": (job.error or "")[:200],
             "attempts": job.attempts, "created_at": _iso(job.created_at)}
            for job in db.query(Job).filter(Job.status == "failed").order_by(Job.created_at.desc()).limit(8).all()
        ],
        "notifications_by_status": _grouped(
            db.query(Notification.status, func.count()).filter(Notification.created_at >= since)
            .group_by(Notification.status).all()
        ),
    })
    return stats


def _integration_analytics(db: Session, tenant: str, since: datetime) -> dict[str, Any]:
    history = db.query(IntegrationHistory).filter(
        IntegrationHistory.tenant_id == tenant, IntegrationHistory.deleted_at.is_(None),
        IntegrationHistory.created_at >= since,
    ).all()
    success = sum(1 for row in history if row.status == "success")
    by_operation: dict[str, Counter] = defaultdict(Counter)
    for row in history:
        by_operation[row.operation_type or "unknown"][row.status or "unknown"] += 1
    errors = Counter(row.error_code for row in history if row.error_code)
    turns = db.query(IntegrationChatTurn).filter(
        IntegrationChatTurn.tenant_id == tenant, IntegrationChatTurn.created_at >= since).all()
    turn_failures = sum(1 for turn in turns if turn.status != "success")
    connectors = _connectors(db, tenant)
    return {
        "connections": connectors,
        "status_counts": dict(Counter(item["status"] for item in connectors)),
        "history": {
            "total": len(history), "success": success, "failed": len(history) - success,
            "success_rate": _pct(success, len(history)),
            "avg_duration_ms": round(mean(row.duration_ms for row in history)) if history else None,
            "p95_duration_ms": _percentile([float(row.duration_ms) for row in history], 95),
            "by_operation": {key: dict(counter) for key, counter in sorted(by_operation.items())},
            "top_errors": [{"code": code, "count": count} for code, count in errors.most_common(5)],
        },
        "chat": {
            "turns": len(turns), "failed": turn_failures, "error_rate": _pct(turn_failures, len(turns)),
            "avg_duration_ms": round(mean(turn.duration_ms for turn in turns)) if turns else None,
            "by_provider": dict(Counter(turn.provider_name or "unknown" for turn in turns)),
        },
    }


def _telemetry_analytics(db: Session, tenant: str) -> dict[str, Any]:
    sensors = db.query(Sensor).filter(Sensor.tenant_id == tenant).all()
    sensor_ids = [sensor.id for sensor in sensors]
    log_sources = db.query(SensorLogSource).filter(SensorLogSource.sensor_id.in_(sensor_ids)).all() if sensor_ids else []
    documents = db.query(SensorDocument.sensor_id, SensorDocument.kind).filter(
        SensorDocument.sensor_id.in_(sensor_ids)).all() if sensor_ids else []
    with_playbook = {sensor_id for sensor_id, kind in documents if kind == "playbook"}
    with_runbook = {sensor_id for sensor_id, kind in documents if kind == "runbook"}
    retention = [source.retention_days for source in log_sources if source.retention_days]
    return {
        "sensors_total": len(sensors),
        "by_category": dict(Counter(sensor.category or "other" for sensor in sensors)),
        "by_status": dict(Counter(sensor.status or "active" for sensor in sensors)),
        "by_criticality": dict(Counter(sensor.criticality or "medium" for sensor in sensors)),
        "log_sources": len(log_sources),
        "eps_total": sum(source.eps_estimate or 0 for source in log_sources),
        "retention_avg_days": round(mean(retention)) if retention else None,
        "without_siem_index": [
            {"sensor": next((s.name for s in sensors if s.id == source.sensor_id), ""), "log_source": source.name}
            for source in log_sources if not source.siem_index
        ][:10],
        "documents_by_kind": dict(Counter(kind for _, kind in documents)),
        "sensors_without_playbook": [sensor.name for sensor in sensors if sensor.id not in with_playbook][:10],
        "sensors_without_runbook": [sensor.name for sensor in sensors if sensor.id not in with_runbook][:10],
        "confluence_published": sum(1 for sensor in sensors if sensor.confluence_page_id),
        "coverage": _tactic_coverage(db, tenant),
        "eps_by_sensor": sorted(
            (
                {"sensor": sensor.name, "eps": sum(source.eps_estimate or 0 for source in log_sources if source.sensor_id == sensor.id)}
                for sensor in sensors
            ),
            key=lambda item: item["eps"], reverse=True,
        )[:8],
    }


def _api_analytics(db: Session, context: AuthContext, since: datetime, now: datetime) -> dict[str, Any]:
    query = db.query(
        UserActivity.module_key, UserActivity.action, UserActivity.method, UserActivity.status_code,
        UserActivity.duration_ms, UserActivity.created_at, UserActivity.actor_user_id,
    ).filter(UserActivity.tenant_id == context.tenant_id, UserActivity.created_at >= since)
    if context.role != "admin":
        query = query.filter(UserActivity.actor_user_id == context.username)
    rows = query.all()

    durations = [float(row.duration_ms or 0) for row in rows]
    errors = sum(1 for row in rows if (row.status_code or 0) >= 400)
    status_classes = Counter(f"{(row.status_code or 0) // 100}xx" for row in rows)
    by_module: dict[str, dict[str, Any]] = defaultdict(lambda: {"requests": 0, "errors": 0, "durations": []})
    by_action: dict[str, list[float]] = defaultdict(list)
    writes = 0
    for row in rows:
        bucket = by_module[row.module_key or "general"]
        bucket["requests"] += 1
        bucket["errors"] += 1 if (row.status_code or 0) >= 400 else 0
        bucket["durations"].append(float(row.duration_ms or 0))
        by_action[row.action].append(float(row.duration_ms or 0))
        if (row.method or "GET").upper() not in {"GET", "HEAD", "OPTIONS"}:
            writes += 1

    hours = min(168, max(24, int((now - since).total_seconds() // 3600)))
    hour_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours - 1)
    hourly = [{"hour": (hour_start + timedelta(hours=offset)).isoformat(), "count": 0, "errors": 0} for offset in range(hours)]
    for row in rows:
        created = _aware(row.created_at)
        if created is None:
            continue
        offset = int((created - hour_start).total_seconds() // 3600)
        if 0 <= offset < hours:
            hourly[offset]["count"] += 1
            hourly[offset]["errors"] += 1 if (row.status_code or 0) >= 400 else 0

    return {
        "requests": len(rows),
        "writes": writes,
        "errors": errors,
        "error_rate": _pct(errors, len(rows)),
        "p50_ms": _percentile(durations, 50),
        "p95_ms": _percentile(durations, 95),
        "max_ms": round(max(durations)) if durations else None,
        "status_classes": {key: status_classes.get(key, 0) for key in ("2xx", "3xx", "4xx", "5xx")},
        "by_module": sorted(
            (
                {"module": module, "requests": data["requests"], "errors": data["errors"],
                 "error_rate": _pct(data["errors"], data["requests"]), "p95_ms": _percentile(data["durations"], 95)}
                for module, data in by_module.items()
            ),
            key=lambda item: item["requests"], reverse=True,
        ),
        "slowest": sorted(
            ({"action": action, "count": len(values), "p95_ms": _percentile(values, 95)} for action, values in by_action.items()),
            key=lambda item: item["p95_ms"] or 0, reverse=True,
        )[:8],
        "active_users": len({row.actor_user_id for row in rows}),
        "hourly": hourly,
    }


def _storage_analytics(db: Session) -> dict[str, Any]:
    settings = get_settings()
    try:
        database_bytes = settings.sqlite_path.stat().st_size if settings.sqlite_path.exists() else 0
    except OSError:
        database_bytes = 0
    return {
        "database_bytes": database_bytes,
        "uploads_bytes": _dir_size(settings.uploads_dir),
        "reports_bytes": _dir_size(settings.reports_dir),
        "exports_bytes": _dir_size(settings.exports_dir),
        "backups_bytes": _dir_size(settings.backups_dir),
        "backup": _last_backup(),
        "documents_total": db.query(func.count()).select_from(Document).scalar() or 0,
        "documents_by_source": _grouped(db.query(Document.source_type, func.count()).group_by(Document.source_type).all()),
        "knowledge_by_type": _grouped(db.query(KnowledgeItem.item_type, func.count()).group_by(KnowledgeItem.item_type).all()),
        "token_estimate_total": int(db.query(func.coalesce(func.sum(Document.token_estimate), 0)).scalar() or 0),
        "analyses_by_kind": _grouped(db.query(Analysis.kind, func.count()).group_by(Analysis.kind).all()),
        "analysis_tokens_total": int(db.query(func.coalesce(func.sum(Analysis.token_estimate), 0)).scalar() or 0),
        "token_mappings": db.query(func.count()).select_from(TokenMapping).scalar() or 0,
        "sensitive_patterns_enabled": db.query(func.count()).select_from(SensitivePattern).filter(SensitivePattern.enabled.is_(True)).scalar() or 0,
        "reports_by_status": _grouped(db.query(Report.status, func.count()).group_by(Report.status).all()),
    }
