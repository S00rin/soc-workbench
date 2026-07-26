"""SQLite database setup using SQLAlchemy 2.0."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()

engine = create_engine(
    settings.resolved_database_url(),
    connect_args={"check_same_thread": False},  # needed for SQLite + threads
    echo=False,
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """Make declared cascade/set-null constraints effective in SQLite."""
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Apply versioned migrations, then create unchanged legacy tables."""
    from . import models  # noqa: F401  (registers all models on Base)
    from .migrations.runner import upgrade_all

    upgrade_all(engine)
    Base.metadata.create_all(bind=engine)
