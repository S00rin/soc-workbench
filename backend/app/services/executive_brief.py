"""Scheduled executive brief: Markdown + PDF + Reports + optional Confluence."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..config import get_settings
from ..logging_config import get_logger
from ..models.atlassian import AtlassianConnection
from ..models.entities import Report
from ..security import AuthContext
from . import dashboard_metrics, notify_event
from .atlassian_http import AtlassianError, AtlassianTransport
from .confluence_provider import ConfluenceProvider
from .pdf_export import export_markdown_pdf
from .sensors import markdown_to_storage
from .settings_service import get_bool, get_int, get_value

logger = get_logger(__name__)

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def _page_url(connection: AtlassianConnection, result: dict, page_id: str) -> str:
    base = connection.base_url.rstrip("/")
    links = result.get("_links") or {}
    webui = links.get("webui") or ""
    if webui:
        if webui.startswith("http"):
            return webui
        wiki = "/wiki" if connection.deployment_type == "cloud" and not webui.startswith("/wiki") else ""
        return f"{base}{wiki}{webui}"
    wiki = "/wiki" if connection.deployment_type == "cloud" else ""
    return f"{base}{wiki}/pages/viewpage.action?pageId={page_id}"


def should_run_today(db: Session, *, now: datetime | None = None) -> bool:
    if not get_bool(db, "brief_enabled", False):
        return False
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    schedule = (get_value(db, "brief_schedule", "daily") or "daily").lower()
    if schedule != "weekly":
        return True
    wanted = WEEKDAYS.get((get_value(db, "brief_weekday", "mon") or "mon").lower()[:3], 0)
    return current.weekday() == wanted


def render_brief(db: Session, context: AuthContext, *, days: int | None = None, language: str | None = None) -> tuple[dict, str]:
    days = days or max(1, get_int(db, "brief_days", 30))
    language = language or get_value(db, "brief_language", "en") or "en"
    summary = dashboard_metrics.executive_summary(db, context, days=days)
    markdown = dashboard_metrics.render_executive_brief(summary, language=language)
    return summary, markdown


def write_pdf(markdown: str, *, title: str, language: str, name: str) -> str:
    path = export_markdown_pdf(markdown, get_settings().reports_dir, name, title=title, language=language)
    return str(path)


def publish_markdown(
    db: Session,
    connection: AtlassianConnection,
    *,
    space: str,
    title: str,
    markdown: str,
    parent_id: str = "",
    page_id: str = "",
) -> dict[str, str]:
    storage = markdown_to_storage(markdown)
    transport = AtlassianTransport(db, connection, "confluence")
    provider = ConfluenceProvider(transport, connection.deployment_type == "cloud")
    try:
        existing = provider.get_page(page_id) if page_id else provider.find_page(space, title)
        if existing:
            page_id = str(existing.get("id", page_id))
            version = (existing.get("version") or {}).get("number", 0)
            result = provider.update_page(page_id, title, storage, version)
            action = "updated"
        else:
            result = provider.create_page(space, title, storage, parent_id)
            page_id = str(result.get("id", ""))
            action = "created"
    finally:
        transport.close()
    return {"action": action, "page_id": page_id, "url": _page_url(connection, result, page_id), "title": title}


def _confluence_connection(db: Session, tenant_id: str) -> AtlassianConnection | None:
    wanted = get_value(db, "brief_confluence_connection_id", "").strip()
    query = db.query(AtlassianConnection).filter(
        AtlassianConnection.tenant_id == tenant_id, AtlassianConnection.enabled.is_(True),
    )
    if wanted.isdigit():
        query = query.filter(AtlassianConnection.id == int(wanted))
    for row in query.order_by(AtlassianConnection.id).all():
        if "confluence" in (row.products or []):
            return row
    return None


def generate(
    db: Session,
    context: AuthContext,
    *,
    days: int | None = None,
    language: str | None = None,
    publish: bool | None = None,
    notify: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    days = days or max(1, get_int(db, "brief_days", 30))
    language = language or get_value(db, "brief_language", "en") or "en"
    summary, markdown = render_brief(db, context, days=days, language=language)
    title = f"Executive brief — {current:%Y-%m-%d} (last {days} days)"
    pdf_name = f"executive-brief-{current:%Y%m%d}-{days}d"
    pdf_path = write_pdf(markdown, title=title, language=language, name=pdf_name)

    report = Report(
        title=title, report_type="executive", language=language,
        date_from=summary["period"]["since"][:10], date_to=summary["period"]["until"][:10],
        data_sources=["dashboard"], content=markdown, versions=[], status="final",
        pdf_path=pdf_path,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    published: dict[str, str] | None = None
    do_publish = get_bool(db, "brief_publish_confluence", False) if publish is None else publish
    if do_publish:
        connection = _confluence_connection(db, context.tenant_id)
        space = get_value(db, "brief_confluence_space", "")
        if connection is None:
            published = {"error": "No enabled Confluence connection for this tenant."}
        elif not space:
            published = {"error": "brief_confluence_space is not configured."}
        else:
            try:
                published = publish_markdown(
                    db, connection, space=space, title=title, markdown=markdown,
                    parent_id=get_value(db, "brief_confluence_parent_id", ""),
                )
                report.confluence_page_id = published["page_id"]
                report.confluence_url = published["url"]
                db.commit()
            except AtlassianError as exc:
                published = {"error": exc.message, "code": exc.code}
                logger.warning("Executive brief Confluence publish failed: %s", exc)

    if notify:
        body = markdown if len(markdown) < 3500 else markdown[:3500] + "\n\n_Truncated._"
        extra = ""
        if published and published.get("url"):
            extra = f"\n\nConfluence: {published['url']}"
        notify_event.deliver(
            db, subject=title, body=body + extra, ref_type="report", ref_id=report.id,
            channel=get_value(db, "brief_notify_channel", "inapp"),
            recipients=get_value(db, "brief_notify_recipients", ""),
        )

    return {
        "id": report.id,
        "report_id": report.id,
        "title": report.title,
        "status": report.status,
        "pdf_path": pdf_path,
        "language": language,
        "days": days,
        "confluence": published,
        "posture": summary["posture"],
    }


def scheduled_run(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    if not should_run_today(db, now=now):
        return {"skipped": True, "reason": "not_scheduled"}
    from ..config import get_settings as _settings

    tenant = _settings().default_tenant_id
    context = AuthContext("scheduler", tenant, "admin")
    return generate(db, context, publish=None, notify=True, now=now)
