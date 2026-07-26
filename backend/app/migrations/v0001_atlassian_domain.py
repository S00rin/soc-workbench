"""Create the tenant-scoped Atlassian integration domain tables.

Revision: 0001_atlassian_domain
Down migration intentionally removes only the new Atlassian tables and leaves
the legacy Jira Settings/Analysis data untouched.
"""
from __future__ import annotations

from sqlalchemy import Engine

from ..database import Base
from ..models import atlassian as _atlassian_models  # noqa: F401

revision = "0001_atlassian_domain"

TABLES = {
    "atlassian_connections",
    "atlassian_field_mappings",
    "integration_history",
    "audit_logs",
    "bulk_operations",
    "bulk_operation_items",
    "idempotency_records",
    "atlassian_content_links",
}


def upgrade(engine: Engine) -> None:
    for table in Base.metadata.sorted_tables:
        if table.name in TABLES:
            table.create(bind=engine, checkfirst=True)


def downgrade(engine: Engine) -> None:
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in TABLES:
            table.drop(bind=engine, checkfirst=True)

