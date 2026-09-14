"""Add operational-signal tables and IoC lifecycle columns."""
from __future__ import annotations

from sqlalchemy import Engine, text

from ..database import Base
from ..models import ops as _ops_models  # noqa: F401
from ..models import entities as _entity_models  # noqa: F401

revision = "0008_ops_signals"

TABLES = {"telemetry_samples", "anomaly_events", "ioc_sightings"}

IOC_COLUMNS = [
    ("status", "VARCHAR(20) DEFAULT 'active' NOT NULL"),
    ("score", "FLOAT DEFAULT 100.0 NOT NULL"),
    ("last_sighted_at", "VARCHAR(60) DEFAULT '' NOT NULL"),
    ("sighting_count", "INTEGER DEFAULT 0 NOT NULL"),
    ("watchlist", "BOOLEAN DEFAULT 0 NOT NULL"),
]

REPORT_COLUMNS = [
    ("pdf_path", "VARCHAR(500) DEFAULT '' NOT NULL"),
    ("confluence_page_id", "VARCHAR(120) DEFAULT '' NOT NULL"),
    ("confluence_url", "VARCHAR(500) DEFAULT '' NOT NULL"),
]


def _columns(engine: Engine, table: str) -> set[str]:
    with engine.connect() as connection:
        rows = connection.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _add_columns(engine: Engine, table: str, columns: list[tuple[str, str]]) -> None:
    existing = _columns(engine, table)
    if not existing:
        return
    with engine.begin() as connection:
        for name, ddl in columns:
            if name not in existing:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def upgrade(engine: Engine) -> None:
    for table in Base.metadata.sorted_tables:
        if table.name in TABLES:
            table.create(bind=engine, checkfirst=True)
    _add_columns(engine, "iocs", IOC_COLUMNS)
    _add_columns(engine, "reports", REPORT_COLUMNS)


def downgrade(engine: Engine) -> None:
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in TABLES:
            table.drop(bind=engine, checkfirst=True)
