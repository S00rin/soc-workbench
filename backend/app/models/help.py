"""Multi-language user/admin help guides (Module 16)."""
from __future__ import annotations

from sqlalchemy import Boolean, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import TimestampMixin


class HelpGuide(Base, TimestampMixin):
    """A single help article. Guides come in matched (slug, language) pairs so
    the UI can offer an English/Farsi toggle for the same topic."""

    __tablename__ = "help_guides"
    __table_args__ = (
        UniqueConstraint("slug", "language", name="uq_help_guide_slug_language"),
        Index("ix_help_guide_audience", "audience", "category", "order_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), index=True)
    language: Mapped[str] = mapped_column(String(10), default="en", index=True)  # en | fa
    audience: Mapped[str] = mapped_column(String(20), default="user", index=True)  # user | admin
    category: Mapped[str] = mapped_column(String(120), default="General")
    title: Mapped[str] = mapped_column(String(240))
    summary: Mapped[str] = mapped_column(String(400), default="")
    content: Mapped[str] = mapped_column(Text, default="")  # markdown
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[str] = mapped_column(String(120), default="")
