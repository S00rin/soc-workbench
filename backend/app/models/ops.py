"""Operational-signal models: telemetry samples, anomaly events, IoC sightings."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import TimestampMixin


class TelemetrySample(Base, TimestampMixin):
    """A point-in-time observation of sensor EPS or feed yield."""

    __tablename__ = "telemetry_samples"
    __table_args__ = (
        Index("ix_telemetry_sample_lookup", "kind", "ref_id", "sampled_at"),
        Index("ix_telemetry_sample_tenant", "tenant_id", "kind", "sampled_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), default="default", index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)  # sensor_log | intel_feed | ioc_feed
    ref_type: Mapped[str] = mapped_column(String(40), default="")
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(240), default="")
    window_minutes: Mapped[int] = mapped_column(Integer, default=15)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    eps: Mapped[float] = mapped_column(Float, default=0.0)
    expected_eps: Mapped[float] = mapped_column(Float, default=0.0)
    yield_count: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(40), default="")  # splunk | collector | estimate
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)


class AnomalyEvent(Base, TimestampMixin):
    """Open/acked/resolved silent-sensor or feed-anomaly alert."""

    __tablename__ = "anomaly_events"
    __table_args__ = (
        Index("ix_anomaly_open", "tenant_id", "status", "kind"),
        Index("ix_anomaly_fingerprint", "tenant_id", "fingerprint"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), default="default", index=True)
    fingerprint: Mapped[str] = mapped_column(String(240), default="", index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)  # silent_sensor | feed_anomaly | eps_spike
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    title: Mapped[str] = mapped_column(String(300), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    ref_type: Mapped[str] = mapped_column(String(40), default="")
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(240), default="")
    observed: Mapped[float] = mapped_column(Float, default=0.0)
    expected: Mapped[float] = mapped_column(Float, default=0.0)
    ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)


class IoCSighting(Base, TimestampMixin):
    """A concrete observation of an IoC, typically from a Splunk retro-hunt."""

    __tablename__ = "ioc_sightings"
    __table_args__ = (Index("ix_ioc_sighting_ioc", "ioc_id", "observed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ioc_id: Mapped[int] = mapped_column(Integer, index=True)
    source: Mapped[str] = mapped_column(String(40), default="splunk", index=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
    query: Mapped[str] = mapped_column(Text, default="")
    index_name: Mapped[str] = mapped_column(String(160), default="")
    observed_at: Mapped[str] = mapped_column(String(60), default="")
    first_seen: Mapped[str] = mapped_column(String(60), default="")
    last_seen: Mapped[str] = mapped_column(String(60), default="")
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    auto: Mapped[bool] = mapped_column(Boolean, default=True)
