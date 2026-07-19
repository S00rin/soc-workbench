"""Add multi-user access control, feature expiry, Wiki.js and integration chat."""
from __future__ import annotations

from sqlalchemy import Engine

from ..database import Base
from ..models import governance as _governance_models  # noqa: F401

revision = "0002_product_governance"

TABLES = {
    "user_accounts",
    "feature_policies",
    "external_connections",
    "integration_chat_sessions",
    "integration_chat_turns",
    "user_activity",
}


def upgrade(engine: Engine) -> None:
    for table in Base.metadata.sorted_tables:
        if table.name in TABLES:
            table.create(bind=engine, checkfirst=True)


def downgrade(engine: Engine) -> None:
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in TABLES:
            table.drop(bind=engine, checkfirst=True)
