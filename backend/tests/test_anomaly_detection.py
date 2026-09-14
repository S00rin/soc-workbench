from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.automation import IntelSource
from app.models.sensors import Sensor, SensorLogSource
from app.services import anomaly_detection

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def _db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return Session(engine)


def test_silent_sensor_opens_when_live_eps_is_zero():
    db = _db()
    sensor = Sensor(tenant_id="default", slug="ngfw", name="NGFW", status="active", category="firewall")
    db.add(sensor)
    db.flush()
    source = SensorLogSource(sensor_id=sensor.id, name="Traffic", siem_index="pan", siem_sourcetype="pan:traffic", eps_estimate=100)
    db.add(source)
    db.commit()

    def search_fn(spl, **_):
        assert "index=" in spl and "pan" in spl
        return {"results": [{"events": "0"}]}

    result = anomaly_detection.run_detection(db, "default", search_fn=search_fn, now=NOW, notify=False)
    assert result["opened"] == 1
    assert result["anomalies"][0]["kind"] == "silent_sensor"
    assert "Silent sensor" in result["anomalies"][0]["title"]
    open_rows = anomaly_detection.list_anomalies(db, "default")
    assert len(open_rows) == 1

    # Recovery: live EPS matches the catalog baseline.
    def recovered(spl, **_):
        return {"results": [{"events": str(100 * 15 * 60)}]}

    result = anomaly_detection.run_detection(db, "default", search_fn=recovered, now=NOW + timedelta(minutes=15), notify=False)
    assert result["opened"] == 0
    assert result["resolved"] == 1
    assert anomaly_detection.list_anomalies(db, "default") == []


def test_feed_yield_collapse_uses_rolling_baseline():
    db = _db()
    source = IntelSource(name="Feed A", url="https://a.example/rss", enabled=True, interval_minutes=60)
    db.add(source)
    db.flush()
    for offset, yield_count in enumerate([12, 11, 10, 13, 12, 9, 11, 10]):
        anomaly_detection.record_feed_sample(
            db, kind="intel_feed", source_id=source.id, name=source.name, yield_count=yield_count,
            now=NOW - timedelta(hours=8 - offset),
        )
    anomaly_detection.record_feed_sample(
        db, kind="intel_feed", source_id=source.id, name=source.name, yield_count=0, now=NOW,
    )
    db.commit()
    result = anomaly_detection.run_detection(
        db, "default", search_fn=lambda *a, **k: {"results": []}, now=NOW, notify=False,
    )
    kinds = {item["kind"] for item in result["anomalies"]}
    assert "feed_anomaly" in kinds
    assert any("Feed A" in item["title"] for item in result["anomalies"])
