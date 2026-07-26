"""Equipment & Sensor Library (Module 17).

A catalog of the security equipment and sensors a SOC operates: what each
device is, what it can do, which logs it emits, how to onboard those logs into
the SIEM, and the runbooks/playbooks analysts follow. Documents can be
published to Confluence through an existing Atlassian connection.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import TimestampMixin


class Sensor(Base, TimestampMixin):
    """A single piece of equipment or a telemetry sensor."""

    __tablename__ = "equipment_sensors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_sensor_tenant_slug"),
        Index("ix_sensor_tenant_category", "tenant_id", "category", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), index=True)
    slug: Mapped[str] = mapped_column(String(160), index=True)
    name: Mapped[str] = mapped_column(String(200))
    vendor: Mapped[str] = mapped_column(String(160), default="")
    product_model: Mapped[str] = mapped_column(String(160), default="")
    category: Mapped[str] = mapped_column(String(40), default="other", index=True)
    description: Mapped[str] = mapped_column(Text, default="")  # markdown intro
    capabilities: Mapped[list] = mapped_column(JSON, default=list)  # [{name, category, description}]
    deployment_notes: Mapped[str] = mapped_column(Text, default="")
    log_format: Mapped[str] = mapped_column(String(40), default="syslog")
    collection_methods: Mapped[list] = mapped_column(JSON, default=list)  # ["syslog", "api", ...]
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active|evaluation|deprecated
    criticality: Mapped[str] = mapped_column(String(20), default="medium")  # low|medium|high|critical
    environment: Mapped[str] = mapped_column(String(20), default="all")  # prod|staging|lab|all
    vendor_url: Mapped[str] = mapped_column(String(400), default="")
    doc_url: Mapped[str] = mapped_column(String(400), default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    mitre_tactics: Mapped[list] = mapped_column(JSON, default=list)  # coverage: tactic names
    owner: Mapped[str] = mapped_column(String(160), default="")
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[str] = mapped_column(String(120), default="")
    confluence_page_id: Mapped[str] = mapped_column(String(120), default="")
    confluence_url: Mapped[str] = mapped_column(String(500), default="")
    confluence_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    log_sources: Mapped[list["SensorLogSource"]] = relationship(
        back_populates="sensor", cascade="all, delete-orphan", order_by="SensorLogSource.order_index",
    )
    documents: Mapped[list["SensorDocument"]] = relationship(
        back_populates="sensor", cascade="all, delete-orphan", order_by="SensorDocument.order_index",
    )


class SensorLogSource(Base, TimestampMixin):
    """A distinct log/event stream a sensor emits (e.g. firewall traffic logs)."""

    __tablename__ = "sensor_log_sources"
    __table_args__ = (Index("ix_log_source_sensor", "sensor_id", "order_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sensor_id: Mapped[int] = mapped_column(ForeignKey("equipment_sensors.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    log_type: Mapped[str] = mapped_column(String(120), default="")  # traffic|threat|auth|...
    format: Mapped[str] = mapped_column(String(40), default="syslog")
    sample: Mapped[str] = mapped_column(Text, default="")  # a representative raw log line
    key_fields: Mapped[list] = mapped_column(JSON, default=list)
    siem_sourcetype: Mapped[str] = mapped_column(String(160), default="")
    siem_index: Mapped[str] = mapped_column(String(160), default="")
    mitre_data_source: Mapped[str] = mapped_column(String(160), default="")
    eps_estimate: Mapped[int] = mapped_column(Integer, default=0)
    retention_days: Mapped[int] = mapped_column(Integer, default=0)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    sensor: Mapped["Sensor"] = relationship(back_populates="log_sources")


class SensorDocument(Base, TimestampMixin):
    """A markdown document attached to a sensor.

    kind: collection (log onboarding) | runbook | playbook | reference | onboarding.
    Playbook-specific hints (severity, trigger, techniques) are optional.
    """

    __tablename__ = "sensor_documents"
    __table_args__ = (Index("ix_sensor_document_sensor_kind", "sensor_id", "kind", "order_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sensor_id: Mapped[int] = mapped_column(ForeignKey("equipment_sensors.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="reference", index=True)
    title: Mapped[str] = mapped_column(String(240))
    summary: Mapped[str] = mapped_column(String(400), default="")
    content: Mapped[str] = mapped_column(Text, default="")  # markdown
    severity: Mapped[str] = mapped_column(String(20), default="")  # playbook: info|low|medium|high|critical
    trigger: Mapped[str] = mapped_column(Text, default="")  # playbook trigger condition
    mitre_techniques: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    updated_by: Mapped[str] = mapped_column(String(120), default="")
    confluence_page_id: Mapped[str] = mapped_column(String(120), default="")
    confluence_url: Mapped[str] = mapped_column(String(500), default="")
    confluence_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sensor: Mapped["Sensor"] = relationship(back_populates="documents")
