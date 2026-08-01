"""Persistent models for intelligence automation and Sorin Code tasks."""
from __future__ import annotations

from sqlalchemy import Boolean, Float, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import TimestampMixin


class IntelSource(Base, TimestampMixin):
    __tablename__ = "intel_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(30), default="rss")
    category: Mapped[str] = mapped_column(String(80), default="Threat Intelligence")
    trust_score: Mapped[float] = mapped_column(Float, default=0.7)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_save_kb: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_extract_iocs: Mapped[bool] = mapped_column(Boolean, default=True)
    summarize: Mapped[bool] = mapped_column(Boolean, default=False)
    last_run_at: Mapped[str] = mapped_column(String(60), default="")
    last_success_at: Mapped[str] = mapped_column(String(60), default="")
    last_error: Mapped[str] = mapped_column(Text, default="")
    failure_count: Mapped[int] = mapped_column(Integer, default=0)


class IoCSource(Base, TimestampMixin):
    __tablename__ = "ioc_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    url: Mapped[str] = mapped_column(Text)
    adapter: Mapped[str] = mapped_column(String(40), index=True)
    trust_score: Mapped[float] = mapped_column(Float, default=0.7)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    last_run_at: Mapped[str] = mapped_column(String(60), default="")
    last_success_at: Mapped[str] = mapped_column(String(60), default="")
    last_error: Mapped[str] = mapped_column(Text, default="")
    failure_count: Mapped[int] = mapped_column(Integer, default=0)


class IoCObservation(Base, TimestampMixin):
    __tablename__ = "ioc_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    ioc_id: Mapped[int] = mapped_column(Integer, index=True)
    source_name: Mapped[str] = mapped_column(String(200), index=True)
    external_id: Mapped[str] = mapped_column(String(200), default="")
    first_seen: Mapped[str] = mapped_column(String(60), default="")
    last_seen: Mapped[str] = mapped_column(String(60), default="")
    valid_until: Mapped[str] = mapped_column(String(60), default="")
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)


class SorinTask(Base, TimestampMixin):
    __tablename__ = "sorin_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), default="Sorin Code task")
    prompt: Mapped[str] = mapped_column(Text)
    workspace: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(20), default="read-only")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=600)
    max_turns: Mapped[int] = mapped_column(Integer, default=10)
    output: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    changed_files: Mapped[list] = mapped_column(JSON, default=list)
    return_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[str] = mapped_column(String(60), default="")
    finished_at: Mapped[str] = mapped_column(String(60), default="")
