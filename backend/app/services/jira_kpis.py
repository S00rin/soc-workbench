"""Deterministic SOC KPI calculations and reusable Jira report templates."""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean, median
from typing import Any


REPORT_TEMPLATES = [
    {
        "id": "daily_soc_operations",
        "name": "Daily SOC Operations",
        "name_fa": "گزارش روزانه عملیات SOC",
        "period": "daily",
        "jql": 'project = "{project_key}" AND (created >= startOfDay() OR updated >= startOfDay()) ORDER BY priority DESC, updated DESC',
        "prompt": (
            "یک گزارش روزانه دقیق از رخدادهای ثبت‌شده در Jira تهیه کن. تعداد موارد جدید و حل‌شده، "
            "رخدادهای بحرانی و با اولویت بالا، موارد بدون مسئول، موارد معوق، ریسک‌های باز و اقدامات شیفت بعدی را بیاور. "
            "فقط به داده‌های موجود استناد کن و برای هر اقدام، کلید Issue را ذکر کن."
        ),
    },
    {
        "id": "weekly_soc_performance",
        "name": "Weekly SOC Performance",
        "name_fa": "گزارش هفتگی عملکرد SOC",
        "period": "weekly",
        "jql": 'project = "{project_key}" AND (created >= startOfWeek() OR updated >= startOfWeek()) ORDER BY priority DESC, updated DESC',
        "prompt": (
            "گزارش هفتگی عملکرد SOC را با تمرکز بر حجم کار، نرخ رفع، backlog، زمان متوسط رفع، رعایت SLA، "
            "توزیع شدت و وضعیت، رخدادهای مهم، گلوگاه‌ها و اقدامات هفته آینده تهیه کن. روند یا نتیجه‌ای را بدون داده نساز."
        ),
    },
    {
        "id": "monthly_soc_executive",
        "name": "Monthly SOC Executive Review",
        "name_fa": "گزارش مدیریتی ماهانه SOC",
        "period": "monthly",
        "jql": 'project = "{project_key}" AND (created >= startOfMonth() OR updated >= startOfMonth()) ORDER BY priority DESC, updated DESC',
        "prompt": (
            "یک گزارش مدیریتی ماهانه برای SOC تهیه کن: خلاصه اجرایی، KPIهای اصلی، وضعیت SLA، رخدادهای بحرانی، "
            "ریسک‌های تکرارشونده، ظرفیت تیم، backlog، دستاوردها و پیشنهادهای قابل اقدام برای ماه بعد. "
            "محدودیت داده و KPIهای غیرقابل محاسبه را شفاف اعلام کن."
        ),
    },
    {
        "id": "shift_handover",
        "name": "SOC Shift Handover",
        "name_fa": "تحویل شیفت SOC",
        "period": "daily",
        "jql": 'project = "{project_key}" AND statusCategory != Done ORDER BY priority DESC, updated ASC',
        "prompt": (
            "گزارش تحویل شیفت بساز و رخدادهای باز را بر اساس شدت مرتب کن. برای هر مورد، وضعیت فعلی، مسئول، "
            "آخرین تغییر، مانع، اقدام بعدی و نیاز به escalation را فقط بر مبنای داده Jira بنویس."
        ),
    },
]


def report_template(template_id: str) -> dict[str, str]:
    try:
        return next(item for item in REPORT_TEMPLATES if item["id"] == template_id)
    except StopIteration as error:
        raise ValueError(f"Unknown report template: {template_id}") from error


def render_template_jql(template_id: str, project_key: str) -> str:
    return report_template(template_id)["jql"].format(project_key=project_key.upper())


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(normalized[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _hours(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None or end < start:
        return None
    return (end - start).total_seconds() / 3600


def _round(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def calculate_soc_kpis(
    issues: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    sla_target_hours: float = 24,
    acknowledgement_field: str = "",
    detection_field: str = "",
) -> dict[str, Any]:
    """Calculate commonly used SOC delivery KPIs from Jira issue fields.

    MTTA and MTTD remain unavailable unless the installation supplies its Jira
    custom timestamp field IDs. This is intentional: a guessed KPI is worse
    than a clearly marked data gap.
    """
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    status_counts: dict[str, int] = {}
    priority_counts: dict[str, int] = {}
    resolution_hours: list[float] = []
    acknowledgement_hours: list[float] = []
    detection_hours: list[float] = []
    open_age_hours: list[float] = []
    sla_met = 0
    resolved = unassigned = overdue = high_critical = 0

    for issue in issues:
        fields = issue.get("fields") or {}
        status = fields.get("status") or {}
        status_name = status.get("name") or "Unknown"
        status_counts[status_name] = status_counts.get(status_name, 0) + 1
        priority_name = (fields.get("priority") or {}).get("name") or "None"
        priority_counts[priority_name] = priority_counts.get(priority_name, 0) + 1
        if priority_name.casefold() in {"highest", "high", "critical", "blocker", "بحرانی", "بالا"}:
            high_critical += 1
        if not fields.get("assignee"):
            unassigned += 1

        created = _parse_datetime(fields.get("created"))
        resolution = _parse_datetime(fields.get("resolutiondate"))
        status_category = (status.get("statusCategory") or {}).get("key", "")
        is_resolved = bool(resolution) or status_category.casefold() == "done"
        if is_resolved:
            resolved += 1
        duration = _hours(created, resolution)
        if duration is not None:
            resolution_hours.append(duration)
            if duration <= sla_target_hours:
                sla_met += 1
        elif created is not None:
            open_age_hours.append(max(0, _hours(created, current) or 0))

        due = _parse_datetime(fields.get("duedate"))
        if not is_resolved and due is not None and due < current:
            overdue += 1

        if acknowledgement_field:
            acknowledgement = _parse_datetime(fields.get(acknowledgement_field))
            elapsed = _hours(created, acknowledgement)
            if elapsed is not None:
                acknowledgement_hours.append(elapsed)
        if detection_field:
            detected = _parse_datetime(fields.get(detection_field))
            elapsed = _hours(detected, created)
            if elapsed is not None:
                detection_hours.append(elapsed)

    total = len(issues)
    resolution_rate = (resolved / total * 100) if total else 0.0
    assignment_coverage = ((total - unassigned) / total * 100) if total else 0.0
    sla_compliance = (sla_met / len(resolution_hours) * 100) if resolution_hours else None
    metrics = {
        "total_issues": {"value": total, "unit": "issues", "label": "Issues in scope"},
        "resolved_issues": {"value": resolved, "unit": "issues", "label": "Resolved"},
        "open_backlog": {"value": total - resolved, "unit": "issues", "label": "Open backlog"},
        "resolution_rate": {"value": _round(resolution_rate), "unit": "%", "label": "Resolution rate"},
        "mttr": {"value": _round(mean(resolution_hours)) if resolution_hours else None, "unit": "hours", "label": "Mean time to resolve"},
        "median_resolution_time": {"value": _round(median(resolution_hours)) if resolution_hours else None, "unit": "hours", "label": "Median resolution time"},
        "mtta": {"value": _round(mean(acknowledgement_hours)) if acknowledgement_hours else None, "unit": "hours", "label": "Mean time to acknowledge"},
        "mttd": {"value": _round(mean(detection_hours)) if detection_hours else None, "unit": "hours", "label": "Mean time to detect"},
        "sla_compliance": {"value": _round(sla_compliance), "unit": "%", "label": f"Resolved within {sla_target_hours:g}h"},
        "mean_open_age": {"value": _round(mean(open_age_hours)) if open_age_hours else None, "unit": "hours", "label": "Mean open age"},
        "unassigned": {"value": unassigned, "unit": "issues", "label": "Unassigned"},
        "assignment_coverage": {"value": _round(assignment_coverage), "unit": "%", "label": "Assignment coverage"},
        "overdue": {"value": overdue, "unit": "issues", "label": "Overdue open issues"},
        "high_critical": {"value": high_critical, "unit": "issues", "label": "High / critical"},
    }
    missing = []
    if not acknowledgement_field:
        missing.append({"metric": "mtta", "reason": "Configure the Jira acknowledgement timestamp field ID."})
    elif not acknowledgement_hours:
        missing.append({"metric": "mtta", "reason": f"No valid values found in {acknowledgement_field}."})
    if not detection_field:
        missing.append({"metric": "mttd", "reason": "Configure the Jira detection/event timestamp field ID."})
    elif not detection_hours:
        missing.append({"metric": "mttd", "reason": f"No valid values found in {detection_field}."})
    if not resolution_hours:
        missing.append({"metric": "mttr", "reason": "No issues contain both created and resolution timestamps."})
        missing.append({"metric": "sla_compliance", "reason": "SLA needs resolved issues with timestamps."})
    return {
        "metrics": metrics,
        "breakdowns": {"status": status_counts, "priority": priority_counts},
        "data_quality": {"issue_count": total, "missing": missing},
        "sla_target_hours": sla_target_hours,
        "calculated_at": current.isoformat(),
    }


def render_markdown_report(template: dict[str, str], project_key: str, result: dict[str, Any]) -> str:
    metrics = result["metrics"]
    def display(name: str) -> str:
        metric = metrics[name]
        return "N/A" if metric["value"] is None else f'{metric["value"]} {metric["unit"]}'

    missing = result["data_quality"]["missing"]
    lines = [
        f'# {template["name_fa"]}', "",
        f'**Project:** {project_key.upper()}',
        f'**Calculated at:** {result["calculated_at"]}', "",
        f'**Jira issues processed:** {result["data_quality"]["issue_count"]} of {result.get("jira_total", result["data_quality"]["issue_count"])}', "",
        "## KPI Summary", "",
        f'- Issues in scope: {display("total_issues")}',
        f'- Resolved: {display("resolved_issues")}',
        f'- Open backlog: {display("open_backlog")}',
        f'- Resolution rate: {display("resolution_rate")}',
        f'- MTTR: {display("mttr")}',
        f'- MTTA: {display("mtta")}',
        f'- MTTD: {display("mttd")}',
        f'- SLA compliance: {display("sla_compliance")}',
        f'- High / critical: {display("high_critical")}',
        f'- Unassigned: {display("unassigned")}',
        f'- Overdue: {display("overdue")}', "",
        "## Status breakdown", "",
    ]
    lines.extend(f'- {name}: {count}' for name, count in result["breakdowns"]["status"].items())
    lines.extend(["", "## Priority breakdown", ""])
    lines.extend(f'- {name}: {count}' for name, count in result["breakdowns"]["priority"].items())
    if missing:
        lines.extend(["", "## Data quality notes", ""])
        lines.extend(f'- {item["metric"].upper()}: {item["reason"]}' for item in missing)
    lines.extend(["", "## Suggested analysis prompt", "", template["prompt"]])
    return "\n".join(lines)
