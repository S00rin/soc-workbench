"""Move legacy assistant-oriented storage names to Sorin terminology."""
from __future__ import annotations

from sqlalchemy import Engine, inspect, text

revision = "0007_sorin_naming"


def _rename_column(engine: Engine, table: str, suffix: str, target: str, excluded: set[str]) -> None:
    columns = {item["name"] for item in inspect(engine).get_columns(table)}
    if target in columns:
        return
    source = next((name for name in columns if name.endswith(suffix) and name not in excluded), None)
    if source:
        with engine.begin() as connection:
            connection.execute(text(f'ALTER TABLE "{table}" RENAME COLUMN "{source}" TO "{target}"'))


def upgrade(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())
    if "documents" in tables:
        _rename_column(engine, "documents", "_analysis", "sorin_analysis", {"sorin_analysis"})
    for table in ("atlassian_connections", "external_connections"):
        if table in tables:
            _rename_column(engine, table, "_enabled", "sorin_enabled", {
                "enabled", "auto_post_enabled", "bulk_auto_post_enabled", "sorin_enabled",
            })
    if "sorin_tasks" not in tables:
        source = next((name for name in tables if name.endswith("_tasks") and name != "sorin_tasks"), None)
        if source:
            with engine.begin() as connection:
                connection.execute(text(f'ALTER TABLE "{source}" RENAME TO "sorin_tasks"'))


def downgrade(engine: Engine) -> None:
    # Product terminology is intentionally not reverted.
    return None
