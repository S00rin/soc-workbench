"""Small migration runner matching SOC Workbench's zero-service deployment.

Usage:
    python -m app.migrations.runner upgrade
    python -m app.migrations.runner downgrade 0001_atlassian_domain
"""
from __future__ import annotations

import sys
from sqlalchemy import Engine, text

from ..database import engine
from . import (
    v0001_atlassian_domain, v0002_product_governance, v0003_price_analyzer,
    v0004_help_guides, v0005_contract_knowledge_link,
)

MIGRATIONS = [
    v0001_atlassian_domain, v0002_product_governance, v0003_price_analyzer,
    v0004_help_guides, v0005_contract_knowledge_link,
]


def _ensure_version_table(db_engine: Engine) -> None:
    with db_engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "revision VARCHAR(120) PRIMARY KEY, applied_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"
        ))


def applied_revisions(db_engine: Engine) -> set[str]:
    _ensure_version_table(db_engine)
    with db_engine.begin() as connection:
        return {row[0] for row in connection.execute(text("SELECT revision FROM schema_migrations"))}


def upgrade_all(db_engine: Engine = engine) -> None:
    applied = applied_revisions(db_engine)
    for migration in MIGRATIONS:
        if migration.revision in applied:
            continue
        migration.upgrade(db_engine)
        with db_engine.begin() as connection:
            connection.execute(
                text("INSERT INTO schema_migrations(revision) VALUES (:revision)"),
                {"revision": migration.revision},
            )


def downgrade(db_engine: Engine, revision: str) -> None:
    target = next((item for item in MIGRATIONS if item.revision == revision), None)
    if target is None:
        raise ValueError(f"Unknown migration: {revision}")
    target.downgrade(db_engine)
    with db_engine.begin() as connection:
        connection.execute(text("DELETE FROM schema_migrations WHERE revision=:revision"), {"revision": revision})


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    command = args[0] if args else "upgrade"
    if command == "upgrade":
        upgrade_all(engine)
        return 0
    if command == "downgrade" and len(args) == 2:
        downgrade(engine, args[1])
        return 0
    print("Usage: python -m app.migrations.runner upgrade|downgrade <revision>")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
