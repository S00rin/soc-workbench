"""Add the Equipment & Sensor Library (sensors, log sources, documents)."""
from __future__ import annotations

from sqlalchemy import Engine

from ..database import Base
from ..models import sensors as _sensor_models  # noqa: F401

revision = "0006_equipment_sensors"

TABLES = {"equipment_sensors", "sensor_log_sources", "sensor_documents"}


def upgrade(engine: Engine) -> None:
    for table in Base.metadata.sorted_tables:
        if table.name in TABLES:
            table.create(bind=engine, checkfirst=True)


def downgrade(engine: Engine) -> None:
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in TABLES:
            table.drop(bind=engine, checkfirst=True)
