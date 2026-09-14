from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.entities import Project, Report
from app.security import AuthContext
from app.services import dashboard_metrics, executive_brief, pdf_export, settings_service

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
ADMIN = AuthContext("admin", "default", "admin", user_id=1)


def _db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = Session(engine)
    settings_service.seed_defaults(session)
    return session


def test_markdown_pdf_writes_a_real_pdf(tmp_path: Path):
    markdown = "# Title\n\n| KPI | Value |\n|---|---|\n| Score | 72 |\n\n- item one\n"
    path = pdf_export.export_markdown_pdf(markdown, tmp_path, "brief", title="SOC Executive Brief", language="en")
    assert path.exists() and path.suffix == ".pdf"
    assert path.read_bytes()[:4] == b"%PDF"


def test_farsi_brief_uses_persian_headings():
    db = _db()
    db.add(Project(name="IR", status="active", health="green", progress=50))
    db.commit()
    summary = dashboard_metrics.executive_summary(db, ADMIN, days=30, now=NOW)
    fa = dashboard_metrics.render_executive_brief(summary, language="fa")
    assert "خلاصه مدیریتی SOC" in fa
    assert "شاخص‌های اصلی" in fa
    en = dashboard_metrics.render_executive_brief(summary, language="en")
    assert "SOC Executive Brief" in en


def test_generate_persists_report_and_pdf(tmp_path: Path, monkeypatch):
    from app.config import Settings

    monkeypatch.setattr("app.services.executive_brief.get_settings", lambda: Settings(data_dir=tmp_path))
    db = _db()
    settings_service.set_value(db, "brief_enabled", "true", "brief")
    settings_service.set_value(db, "brief_publish_confluence", "false", "brief")
    result = executive_brief.generate(db, ADMIN, days=7, language="en", publish=False, notify=False, now=NOW)
    assert result["id"]
    report = db.get(Report, result["id"])
    assert report is not None
    assert report.report_type == "executive"
    assert report.pdf_path.endswith(".pdf")
    assert Path(report.pdf_path).exists()
    assert "SOC Executive Brief" in report.content


def test_weekly_schedule_skips_off_days():
    db = _db()
    settings_service.set_value(db, "brief_enabled", "true", "brief")
    settings_service.set_value(db, "brief_schedule", "weekly", "brief")
    settings_service.set_value(db, "brief_weekday", "mon", "brief")
    wednesday = datetime(2026, 9, 9, 6, 0, tzinfo=timezone.utc)  # Wednesday
    monday = datetime(2026, 9, 7, 6, 0, tzinfo=timezone.utc)
    assert executive_brief.should_run_today(db, now=wednesday) is False
    assert executive_brief.should_run_today(db, now=monday) is True
