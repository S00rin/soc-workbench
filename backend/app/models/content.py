"""Content models: processed documents, knowledge base, internet intelligence."""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import TimestampMixin


class Document(Base, TimestampMixin):
    """A processed input (file/text/url/etc.) with all its versions."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), default="Untitled")
    source_type: Mapped[str] = mapped_column(String(40), index=True)  # file/text/url/...
    source_ref: Mapped[str] = mapped_column(Text, default="")  # filename or url
    mime: Mapped[str] = mapped_column(String(120), default="")
    stored_path: Mapped[str] = mapped_column(Text, default="")  # relative to uploads

    # Versions (Module 2)
    original_text: Mapped[str] = mapped_column(Text, default="")
    markdown: Mapped[str] = mapped_column(Text, default="")
    protected_markdown: Mapped[str] = mapped_column(Text, default="")
    optimized_markdown: Mapped[str] = mapped_column(Text, default="")
    ai_analysis: Mapped[str] = mapped_column(Text, default="")

    summary: Mapped[str] = mapped_column(Text, default="")
    entities: Mapped[dict] = mapped_column(JSON, default=dict)  # keywords, iocs, ips...
    protection_mode: Mapped[str] = mapped_column(String(20), default="mask")
    optimization_mode: Mapped[str] = mapped_column(String(20), default="balanced")
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="processed", index=True)


class KnowledgeItem(Base, TimestampMixin):
    """SOC knowledge-base entry (Module 8)."""

    __tablename__ = "knowledge_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    item_type: Mapped[str] = mapped_column(String(60), default="note", index=True)
    content: Mapped[str] = mapped_column(Text, default="")  # markdown
    summary: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(80), default="", index=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(200), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    related_project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    related_jira: Mapped[str] = mapped_column(String(60), default="")
    related_splunk: Mapped[str] = mapped_column(Text, default="")
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")


class IntelItem(Base, TimestampMixin):
    """Collected internet intelligence item (Module 5)."""

    __tablename__ = "intel_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(400), index=True)
    original_title: Mapped[str] = mapped_column(String(400), default="")
    source: Mapped[str] = mapped_column(String(200), default="")
    url: Mapped[str] = mapped_column(Text, default="", index=True)
    published_at: Mapped[str] = mapped_column(String(60), default="")
    original_language: Mapped[str] = mapped_column(String(10), default="")
    summary_fa: Mapped[str] = mapped_column(Text, default="")
    summary_en: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(80), default="Other", index=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    entities: Mapped[dict] = mapped_column(JSON, default=dict)  # iocs, cves, vendors...
    relevance: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str] = mapped_column(Text, default="")
    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, default="")
