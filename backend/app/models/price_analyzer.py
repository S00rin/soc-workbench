"""Project price analyzer: contract ingestion, effort estimation, cost
calculation, WBS/Gantt scheduling and RACI matrix (Module 17)."""
from __future__ import annotations

import copy

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import TimestampMixin

# Defaults target the Iranian market: Toman currency and per-hour rates in
# Toman. All values are editable per contract from the UI, so these are just
# sensible starting points, not fixed prices.
DEFAULT_COEFFICIENTS = {
    "currency": "تومان",
    "hours_per_day": 8.0,
    "rates": {
        "project_manager": 500000.0,
        "business_analyst": 400000.0,
        "developer": 450000.0,
        "qa_engineer": 300000.0,
        "designer": 400000.0,
        "devops_engineer": 500000.0,
        "security_engineer": 550000.0,
        "unassigned": 250000.0,
    },
    "overhead_percent": 10.0,
    "contingency_percent": 10.0,
    "tax_percent": 9.0,
    "discount_percent": 0.0,
}


def default_coefficients() -> dict:
    """A fresh deep copy so per-contract edits never leak into the shared
    default (the nested ``rates`` dict must not be aliased across rows)."""
    return copy.deepcopy(DEFAULT_COEFFICIENTS)


class Contract(Base, TimestampMixin):
    """A single contract/proposal under analysis."""

    __tablename__ = "price_analyzer_contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(240), index=True)
    customer: Mapped[str] = mapped_column(String(200), default="")
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    language: Mapped[str] = mapped_column(String(10), default="fa")  # en | fa
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)  # draft|analyzed|finalized
    source_type: Mapped[str] = mapped_column(String(20), default="text")  # file | text
    source_ref: Mapped[str] = mapped_column(String(300), default="")
    stored_path: Mapped[str] = mapped_column(String(300), default="")
    source_text: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    coefficients: Mapped[dict] = mapped_column(JSON, default=default_coefficients)
    schedule_start: Mapped[str] = mapped_column(String(30), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(120), default="")
    # Set once the contract's content has been pushed to the central knowledge
    # base, so re-pushing updates that entry instead of creating duplicates.
    knowledge_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ContractSection(Base, TimestampMixin):
    """A single scope/clause of the contract with an editable effort estimate."""

    __tablename__ = "price_analyzer_sections"
    __table_args__ = (Index("ix_pa_section_contract_order", "contract_id", "order_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("price_analyzer_contracts.id", ondelete="CASCADE"), index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(60), default="development")
    role: Mapped[str] = mapped_column(String(60), default="unassigned")
    excerpt: Mapped[str] = mapped_column(Text, default="")
    estimated_hours: Mapped[float] = mapped_column(Float, default=0.0)
    adjusted_hours: Mapped[float] = mapped_column(Float, default=0.0)
    hourly_rate_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class WBSItem(Base, TimestampMixin):
    """A node in the 3-level work breakdown structure / Gantt schedule."""

    __tablename__ = "price_analyzer_wbs_items"
    __table_args__ = (Index("ix_pa_wbs_contract_order", "contract_id", "order_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("price_analyzer_contracts.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("price_analyzer_wbs_items.id", ondelete="CASCADE"), nullable=True, index=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("price_analyzer_sections.id", ondelete="SET NULL"), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=1)  # 1, 2 or 3
    code: Mapped[str] = mapped_column(String(20), default="1")
    title: Mapped[str] = mapped_column(String(300))
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    start_date: Mapped[str] = mapped_column(String(30), default="")
    end_date: Mapped[str] = mapped_column(String(30), default="")
    duration_days: Mapped[float] = mapped_column(Float, default=0.0)
    percent_complete: Mapped[int] = mapped_column(Integer, default=0)
    assignee: Mapped[str] = mapped_column(String(160), default="")


class RACIEntry(Base, TimestampMixin):
    """One (WBS item, participant) assignment in the editable RACI matrix."""

    __tablename__ = "price_analyzer_raci_entries"
    __table_args__ = (Index("ix_pa_raci_contract_item", "contract_id", "wbs_item_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("price_analyzer_contracts.id", ondelete="CASCADE"), index=True)
    wbs_item_id: Mapped[int] = mapped_column(ForeignKey("price_analyzer_wbs_items.id", ondelete="CASCADE"), index=True)
    participant: Mapped[str] = mapped_column(String(160))
    raci: Mapped[str] = mapped_column(String(1), default="C")  # R | A | C | I
