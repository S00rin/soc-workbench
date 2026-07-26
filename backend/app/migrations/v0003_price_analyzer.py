"""Add the project price analyzer: contracts, sections, WBS and RACI tables."""
from __future__ import annotations

from sqlalchemy import Engine

from ..database import Base
from ..models import price_analyzer as _price_analyzer_models  # noqa: F401

revision = "0003_price_analyzer"

TABLES = {
    "price_analyzer_contracts",
    "price_analyzer_sections",
    "price_analyzer_wbs_items",
    "price_analyzer_raci_entries",
}


def upgrade(engine: Engine) -> None:
    for table in Base.metadata.sorted_tables:
        if table.name in TABLES:
            table.create(bind=engine, checkfirst=True)


def downgrade(engine: Engine) -> None:
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in TABLES:
            table.drop(bind=engine, checkfirst=True)
