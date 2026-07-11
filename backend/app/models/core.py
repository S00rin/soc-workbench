"""Core operational models: settings, jobs, sensitive patterns, token mapping."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import TimestampMixin


class Setting(Base, TimestampMixin):
    """Key/value application settings. Secrets stored encrypted (is_secret)."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, default="")
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str] = mapped_column(String(60), default="general", index=True)


class Job(Base, TimestampMixin):
    """Background job / connector-run status record."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(60), index=True)  # e.g. document, intel, llm
    # pending | running | completed | failed
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    ref_type: Mapped[str] = mapped_column(String(60), default="")  # linked entity type
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class SensitivePattern(Base, TimestampMixin):
    """User-defined sensitive-data pattern (regex or literal)."""

    __tablename__ = "sensitive_patterns"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(80))  # e.g. ORGANIZATION, CUSTOMER
    pattern: Mapped[str] = mapped_column(Text)
    is_regex: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    token_prefix: Mapped[str] = mapped_column(String(40), default="CUSTOM")


class TokenMapping(Base, TimestampMixin):
    """Local mapping token <-> original value. NEVER sent to an LLM.

    original_value is stored encrypted at rest.
    """

    __tablename__ = "token_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(80), index=True)
    original_encrypted: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(String(80), default="")
    scope: Mapped[str] = mapped_column(String(80), default="global", index=True)
