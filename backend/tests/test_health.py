from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.entities import IoC
from app.models.ops import AnomalyEvent
from app.services import health

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def _db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def test_readiness_is_ready_when_sqlite_and_disk_work(tmp_path, monkeypatch):
    from app.config import Settings

    monkeypatch.setattr("app.services.health.get_settings", lambda: Settings(data_dir=tmp_path))
    engine, db = _db()
    try:
        payload = health.readiness(db)
        assert payload["status"] == "ready"
        assert payload["checks"]["database"]["ok"] is True
        assert payload["checks"]["disk"]["ok"] is True
        assert payload["version"] == health.APP_VERSION
    finally:
        db.close()
        engine.dispose()


def test_prometheus_text_exports_gauges():
    engine, db = _db()
    try:
        db.add(IoC(value="1.2.3.4", ioc_type="ipv4", severity="high", watchlist=True, status="watchlist"))
        db.add(AnomalyEvent(kind="silent_sensor", status="open", title="Silent", tenant_id="default", fingerprint="x"))
        db.commit()
        text_body = health.prometheus_text(db, now=NOW)
        assert "soc_workbench_up 1" in text_body
        assert 'soc_workbench_iocs{state="watchlist"} 1' in text_body
        assert 'soc_workbench_anomalies_open{kind="silent_sensor"} 1' in text_body
        assert "soc_workbench_backup_age_hours" in text_body
    finally:
        db.close()
        engine.dispose()


def test_readiness_reports_database_failure(tmp_path, monkeypatch):
    from app.config import Settings

    monkeypatch.setattr("app.services.health.get_settings", lambda: Settings(data_dir=tmp_path))
    engine, db = _db()
    db.execute = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down"))  # type: ignore[method-assign]
    payload = health.readiness(db)
    db.close()
    engine.dispose()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["database"]["ok"] is False
