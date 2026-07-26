"""Tests for the Equipment & Sensor Library service: seed data, coverage,
markdown export and Confluence storage rendering."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
import app.models  # noqa: F401  (register all models on Base)
from app.models.sensors import Sensor, SensorDocument
from app.services import sensors as svc


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_seed_creates_reference_sensors_with_children(db):
    svc.seed_default_sensors(db, "local")
    rows = db.query(Sensor).all()
    assert len(rows) == len(svc.SEED_SENSORS)
    for row in rows:
        assert row.is_builtin is True
        assert row.name.strip()
        assert row.log_sources, f"{row.slug} should have log sources"
        assert row.documents, f"{row.slug} should have documents"
        assert row.category in svc.CATEGORIES


def test_seed_is_idempotent_and_preserves_edits(db):
    svc.seed_default_sensors(db, "local")
    row = db.query(Sensor).filter(Sensor.slug == "palo-alto-ngfw").first()
    row.description = "Edited by an analyst."
    db.commit()

    svc.seed_default_sensors(db, "local")  # simulate a restart re-running the seed
    assert db.query(Sensor).count() == len(svc.SEED_SENSORS)  # no duplicates
    reloaded = db.query(Sensor).filter(Sensor.slug == "palo-alto-ngfw").first()
    assert reloaded.description == "Edited by an analyst."  # never overwritten


def test_seed_is_tenant_scoped(db):
    svc.seed_default_sensors(db, "tenant-a")
    svc.seed_default_sensors(db, "tenant-b")
    assert db.query(Sensor).filter(Sensor.tenant_id == "tenant-a").count() == len(svc.SEED_SENSORS)
    assert db.query(Sensor).filter(Sensor.tenant_id == "tenant-b").count() == len(svc.SEED_SENSORS)


def test_coverage_summary_counts_documents_and_tactics(db):
    svc.seed_default_sensors(db, "local")
    rows = db.query(Sensor).all()
    summary = svc.coverage_summary(rows)
    assert summary["total_sensors"] == len(svc.SEED_SENSORS)
    assert summary["log_sources"] > 0
    assert summary["playbooks"] >= 1
    assert summary["runbooks"] >= 1
    assert 0 < summary["tactics_covered"] <= summary["tactics_total"]
    assert sum(summary["by_category"].values()) == len(rows)


def test_sensor_to_markdown_includes_sections(db):
    svc.seed_default_sensors(db, "local")
    row = db.query(Sensor).filter(Sensor.slug == "palo-alto-ngfw").first()
    md = svc.sensor_to_markdown(row)
    assert md.startswith("# Palo Alto Networks NGFW")
    assert "## Capabilities" in md
    assert "## Log sources" in md
    assert "## Playbook" in md
    assert "| Name | Type | Format" in md  # log source table


def test_markdown_to_storage_wraps_banner_and_renders_tables(db):
    svc.seed_default_sensors(db, "local")
    row = db.query(Sensor).filter(Sensor.slug == "zeek-network-sensor").first()
    storage = svc.markdown_to_storage(svc.sensor_to_markdown(row))
    assert "ac:structured-macro" in storage  # info banner macro
    assert "This page is published from SOC Workbench" in storage
    assert "<table>" in storage  # tables extension active


def test_document_to_markdown_includes_playbook_hints(db):
    svc.seed_default_sensors(db, "local")
    doc = (
        db.query(SensorDocument)
        .filter(SensorDocument.kind == "playbook", SensorDocument.severity != "")
        .first()
    )
    md = svc.document_to_markdown(doc)
    assert doc.title in md
    assert "Severity" in md
    assert "Trigger" in md


def test_confluence_title_differs_for_document(db):
    svc.seed_default_sensors(db, "local")
    sensor = db.query(Sensor).filter(Sensor.slug == "palo-alto-ngfw").first()
    doc = sensor.documents[0]
    assert svc.confluence_title(sensor) == "Palo Alto Networks NGFW — Sensor Profile"
    assert doc.title in svc.confluence_title(sensor, doc)
