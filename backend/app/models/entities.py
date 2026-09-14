"""Domain entities: IoCs, projects, reports, prompts, notifications, analyses."""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import TimestampMixin


class IoC(Base, TimestampMixin):
    """Indicator of Compromise (Module 9)."""

    __tablename__ = "iocs"

    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(String(500), index=True)
    ioc_type: Mapped[str] = mapped_column(String(40), index=True)  # ipv4/domain/hash...
    source: Mapped[str] = mapped_column(String(200), default="")
    confidence: Mapped[str] = mapped_column(String(20), default="medium")
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    first_seen: Mapped[str] = mapped_column(String(60), default="")
    last_seen: Mapped[str] = mapped_column(String(60), default="")
    expires_at: Mapped[str] = mapped_column(String(60), default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    related_malware: Mapped[str] = mapped_column(String(200), default="")
    related_actor: Mapped[str] = mapped_column(String(200), default="")
    related_incident: Mapped[str] = mapped_column(String(200), default="")
    related_customer: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    false_positive: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active|watchlist|decaying|expired|retired
    score: Mapped[float] = mapped_column(Float, default=100.0)
    last_sighted_at: Mapped[str] = mapped_column(String(60), default="")
    sighting_count: Mapped[int] = mapped_column(Integer, default=0)
    watchlist: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class Project(Base, TimestampMixin):
    """Lightweight project tracking (Module 10)."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    customer: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    start_date: Mapped[str] = mapped_column(String(30), default="")
    end_date: Mapped[str] = mapped_column(String(30), default="")
    manager: Mapped[str] = mapped_column(String(120), default="")
    tech_owner: Mapped[str] = mapped_column(String(120), default="")
    health: Mapped[str] = mapped_column(String(20), default="green")  # green/yellow/red
    progress: Mapped[int] = mapped_column(Integer, default=0)
    jira_project: Mapped[str] = mapped_column(String(60), default="")
    splunk_env: Mapped[str] = mapped_column(String(120), default="")
    risks: Mapped[list] = mapped_column(JSON, default=list)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    milestones: Mapped[list] = mapped_column(JSON, default=list)
    action_items: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")


class Report(Base, TimestampMixin):
    """Generated report with versions (Module 11)."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    report_type: Mapped[str] = mapped_column(String(60), index=True)
    language: Mapped[str] = mapped_column(String(10), default="en")
    detail_level: Mapped[str] = mapped_column(String(20), default="balanced")
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer: Mapped[str] = mapped_column(String(200), default="")
    date_from: Mapped[str] = mapped_column(String(30), default="")
    date_to: Mapped[str] = mapped_column(String(30), default="")
    data_sources: Mapped[list] = mapped_column(JSON, default=list)
    content: Mapped[str] = mapped_column(Text, default="")  # markdown
    versions: Mapped[list] = mapped_column(JSON, default=list)  # [{ts, content}]
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    pdf_path: Mapped[str] = mapped_column(String(500), default="")
    confluence_page_id: Mapped[str] = mapped_column(String(120), default="")
    confluence_url: Mapped[str] = mapped_column(String(500), default="")


class Prompt(Base, TimestampMixin):
    """Reusable prompt template (Module 13)."""

    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(80), default="Custom", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    user_template: Mapped[str] = mapped_column(Text, default="")
    variables: Mapped[list] = mapped_column(JSON, default=list)
    model: Mapped[str] = mapped_column(String(80), default="")
    max_tokens: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str] = mapped_column(String(10), default="en")
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)


class Notification(Base, TimestampMixin):
    """Notification delivery record (Module 12)."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(40), index=True)  # email/webhook/telegram
    subject: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    recipients: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    ref_type: Mapped[str] = mapped_column(String(40), default="")
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Analysis(Base, TimestampMixin):
    """Saved analysis result (Jira / Splunk / LLM) with history (Modules 4/6/7)."""

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)  # jira/splunk/llm
    title: Mapped[str] = mapped_column(String(300), default="")
    query: Mapped[str] = mapped_column(Text, default="")  # JQL / SPL / instruction
    input_summary: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(Text, default="")  # markdown result
    raw: Mapped[dict] = mapped_column(JSON, default=dict)  # structured data
    model: Mapped[str] = mapped_column(String(80), default="")
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
