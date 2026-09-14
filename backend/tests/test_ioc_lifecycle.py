from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.automation import IoCObservation
from app.models.entities import IoC
from app.models.ops import IoCSighting
from app.services import ioc_lifecycle

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def _db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return Session(engine)


def test_decay_expires_stale_indicators_and_promotes_fresh_high_score():
    db = _db()
    fresh = IoC(
        value="8.8.8.8", ioc_type="ipv4", severity="critical", confidence="high",
        first_seen=NOW.isoformat(), last_seen=NOW.isoformat(), created_at=NOW, updated_at=NOW,
    )
    stale = IoC(
        value="old.example", ioc_type="domain", severity="low", confidence="low",
        first_seen=(NOW - timedelta(days=90)).isoformat(),
        last_seen=(NOW - timedelta(days=90)).isoformat(),
        created_at=NOW - timedelta(days=90), updated_at=NOW,
    )
    fp = IoC(value="benign.test", ioc_type="domain", false_positive=True, created_at=NOW, updated_at=NOW)
    db.add_all([fresh, stale, fp])
    db.flush()
    db.add(IoCObservation(ioc_id=fresh.id, source_name="ThreatFox", confidence_score=0.95))
    db.commit()

    counts = ioc_lifecycle.refresh_scores(db, now=NOW)
    db.refresh(fresh)
    db.refresh(stale)
    db.refresh(fp)
    assert fp.status == "retired" and fp.score == 0
    assert stale.status == "expired"
    assert fresh.watchlist is True
    assert fresh.status == "watchlist"
    assert fresh.score > 60
    assert counts["promoted"] == 1


def test_retro_hunt_records_sightings_from_splunk_rows():
    db = _db()
    ioc = IoC(value="evil.example", ioc_type="domain", severity="high", status="active", created_at=NOW, updated_at=NOW)
    other = IoC(value="quiet.example", ioc_type="domain", severity="medium", status="active", created_at=NOW, updated_at=NOW)
    db.add_all([ioc, other])
    db.commit()

    def search_fn(spl, **_):
        assert "evil.example" in spl
        return {"results": [
            {"_raw": "dns query evil.example", "_time": NOW.timestamp()},
            {"dest": "evil.example", "_time": (NOW - timedelta(hours=1)).timestamp()},
        ]}

    result = ioc_lifecycle.retro_hunt(db, search_fn=search_fn, earliest="-24h", now=NOW)
    assert result["sighted"] == 1
    db.refresh(ioc)
    db.refresh(other)
    assert ioc.sighting_count == 1
    assert ioc.last_sighted_at
    assert other.sighting_count == 0
    assert db.query(IoCSighting).filter(IoCSighting.ioc_id == ioc.id).count() == 1


def test_watchlist_csv_and_stix_export():
    db = _db()
    ioc = IoC(
        value="1.2.3.4", ioc_type="ipv4", severity="high", watchlist=True, status="watchlist",
        score=88, tags=["botnet"], created_at=NOW, updated_at=NOW,
    )
    db.add(ioc)
    db.commit()
    rows = ioc_lifecycle.watchlist_query(db, scope="watchlist")
    csv_body = ioc_lifecycle.export_csv(rows)
    assert "1.2.3.4" in csv_body and "watchlist" in csv_body
    bundle = ioc_lifecycle.export_stix(rows, now=NOW)
    assert bundle["type"] == "bundle"
    assert bundle["objects"][0]["pattern"] == "[ipv4-addr:value = '1.2.3.4']"
    assert bundle["objects"][0]["pattern_type"] == "stix"
