"""Link a price-analyzer contract to its central knowledge-base entry.

Adds ``knowledge_item_id`` to ``price_analyzer_contracts``. On a fresh
database the column is already present (the table is created from the current
model metadata by v0003), so this migration is written to be idempotent and
only ALTERs an existing table that predates the column.
"""
from __future__ import annotations

from sqlalchemy import Engine, text

revision = "0005_contract_knowledge_link"

TABLE = "price_analyzer_contracts"
COLUMN = "knowledge_item_id"


def _has_column(engine: Engine) -> bool:
    with engine.connect() as connection:
        rows = connection.execute(text(f"PRAGMA table_info({TABLE})")).fetchall()
    return any(row[1] == COLUMN for row in rows)


def upgrade(engine: Engine) -> None:
    # PRAGMA returns no rows if the table doesn't exist yet; in that case v0003
    # will create it (with the column) from metadata, so there's nothing to do.
    with engine.connect() as connection:
        exists = connection.execute(text(f"PRAGMA table_info({TABLE})")).fetchall()
    if not exists or _has_column(engine):
        return
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} INTEGER"))


def downgrade(engine: Engine) -> None:
    # SQLite can drop a column since 3.35; ignore if unsupported/absent.
    if not _has_column(engine):
        return
    with engine.begin() as connection:
        try:
            connection.execute(text(f"ALTER TABLE {TABLE} DROP COLUMN {COLUMN}"))
        except Exception:  # noqa: BLE001 - older SQLite cannot drop columns
            pass
