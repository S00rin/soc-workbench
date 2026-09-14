"""Silent-sensor and feed-anomaly detection from EPS and yield baselines.

Sensor EPS is sampled from Splunk when a log source has a SIEM index. Feed
yield is sampled from intel/IoC collection runs. Each stream learns a rolling
baseline; a drop below the configured ratio (or a near-zero sample against a
non-zero baseline) opens an anomaly that is notified and shown on the
dashboards.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any

from sqlalchemy.orm import Session

from ..logging_config import get_logger
from ..models.automation import IntelSource, IoCSource
from ..models.ops import AnomalyEvent, TelemetrySample
from ..models.sensors import Sensor, SensorLogSource
from . import notify_event
from .settings_service import get_all_resolved, get_bool, get_float, get_int, get_value
from .splunk_client import SplunkError, client_from_settings

logger = get_logger(__name__)

SearchFn = Callable[..., dict]


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _now(value: datetime | None) -> datetime:
    return (_aware(value) or datetime.now(timezone.utc)).astimezone(timezone.utc)


def serialize(row: AnomalyEvent) -> dict[str, Any]:
    return {
        "id": row.id, "kind": row.kind, "severity": row.severity, "title": row.title,
        "detail": row.detail, "ref_type": row.ref_type, "ref_id": row.ref_id, "name": row.name,
        "observed": row.observed, "expected": row.expected, "ratio": row.ratio,
        "status": row.status, "first_seen": row.first_seen.isoformat() if row.first_seen else None,
        "last_seen": row.last_seen.isoformat() if row.last_seen else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "extra": row.extra or {},
    }


def record_feed_sample(
    db: Session,
    *,
    kind: str,
    source_id: int,
    name: str,
    yield_count: int,
    tenant_id: str = "default",
    now: datetime | None = None,
    window_minutes: int = 60,
) -> TelemetrySample:
    current = _now(now)
    sample = TelemetrySample(
        tenant_id=tenant_id, kind=kind, ref_type="intel_source" if kind == "intel_feed" else "ioc_source",
        ref_id=source_id, name=name, window_minutes=window_minutes, yield_count=yield_count,
        event_count=yield_count, source="collector", sampled_at=current,
    )
    db.add(sample)
    db.flush()
    return sample


def _event_count(payload: dict) -> int:
    rows = payload.get("results") or []
    if rows:
        row = rows[0]
        for key in ("events", "count", "total"):
            if key in row:
                try:
                    return int(float(row[key]))
                except (TypeError, ValueError):
                    continue
        return len(rows)
    try:
        return int(payload.get("count") or 0)
    except (TypeError, ValueError):
        return 0


def _escape_spl(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _mean(values: list[float]) -> float:
    return float(mean(values)) if values else 0.0


def _open_event(
    db: Session,
    *,
    tenant_id: str,
    kind: str,
    severity: str,
    title: str,
    detail: str,
    ref_type: str,
    ref_id: int | None,
    name: str,
    observed: float,
    expected: float,
    extra: dict,
    now: datetime,
) -> tuple[AnomalyEvent, bool]:
    fingerprint = f"{kind}:{ref_type}:{ref_id or 0}:{name}"
    ratio = round(observed / expected, 4) if expected else None
    existing = (
        db.query(AnomalyEvent)
        .filter(AnomalyEvent.tenant_id == tenant_id, AnomalyEvent.fingerprint == fingerprint, AnomalyEvent.status == "open")
        .first()
    )
    if existing:
        existing.last_seen = now
        existing.observed = observed
        existing.expected = expected
        existing.ratio = ratio
        existing.detail = detail
        existing.severity = severity
        existing.extra = extra
        return existing, False
    row = AnomalyEvent(
        tenant_id=tenant_id, fingerprint=fingerprint, kind=kind, severity=severity,
        title=title, detail=detail, ref_type=ref_type, ref_id=ref_id, name=name,
        observed=observed, expected=expected, ratio=ratio, status="open",
        first_seen=now, last_seen=now, extra=extra,
    )
    db.add(row)
    db.flush()
    return row, True


def _resolve_missing(db: Session, tenant_id: str, kind: str, fingerprints: set[str], now: datetime) -> int:
    resolved = 0
    open_rows = db.query(AnomalyEvent).filter(
        AnomalyEvent.tenant_id == tenant_id, AnomalyEvent.kind == kind, AnomalyEvent.status == "open",
    ).all()
    for row in open_rows:
        if row.fingerprint in fingerprints:
            continue
        row.status = "resolved"
        row.resolved_at = now
        resolved += 1
    return resolved


def collect_sensor_samples(
    db: Session,
    tenant_id: str,
    *,
    search_fn: SearchFn | None = None,
    now: datetime | None = None,
    window_minutes: int | None = None,
) -> list[TelemetrySample]:
    current = _now(now)
    window = window_minutes or max(5, get_int(db, "anomaly_splunk_window_minutes", 15))
    if search_fn is None:
        client = client_from_settings(get_all_resolved(db))
        if client is None:
            return []
        def search_fn(spl: str, earliest: str = "", latest: str = "now", **_: Any) -> dict:  # noqa: ARG001
            return client.search(spl, earliest=earliest or f"-{window}m", latest=latest, max_results=20)
    sensors = db.query(Sensor).filter(Sensor.tenant_id == tenant_id, Sensor.status == "active").all()
    samples: list[TelemetrySample] = []
    for sensor in sensors:
        for source in sensor.log_sources or []:
            index_name = (source.siem_index or "").strip()
            if not index_name:
                continue
            sourcetype = (source.siem_sourcetype or "").strip()
            parts = [f'index="{_escape_spl(index_name)}"']
            if sourcetype:
                parts.append(f'sourcetype="{_escape_spl(sourcetype)}"')
            spl = "search " + " ".join(parts) + " | stats count as events"
            try:
                payload = search_fn(spl, earliest=f"-{window}m", latest="now")
                events = _event_count(payload)
            except (SplunkError, Exception) as exc:  # noqa: BLE001
                logger.warning("EPS sample failed for %s/%s: %s", sensor.name, source.name, exc)
                continue
            eps = events / max(1, window * 60)
            sample = TelemetrySample(
                tenant_id=tenant_id, kind="sensor_log", ref_type="sensor_log_source",
                ref_id=source.id, name=f"{sensor.name} / {source.name}",
                window_minutes=window, event_count=events, eps=round(eps, 4),
                expected_eps=float(source.eps_estimate or 0), source="splunk",
                sampled_at=current, extra={"sensor_id": sensor.id, "index": index_name, "sourcetype": sourcetype},
            )
            db.add(sample)
            samples.append(sample)
    db.flush()
    return samples


def _history_eps(db: Session, ref_id: int, before: datetime, limit: int = 12) -> list[float]:
    rows = (
        db.query(TelemetrySample)
        .filter(
            TelemetrySample.kind == "sensor_log", TelemetrySample.ref_id == ref_id,
            TelemetrySample.sampled_at < before,
        )
        .order_by(TelemetrySample.sampled_at.desc())
        .limit(limit)
        .all()
    )
    return [row.eps for row in rows]


def _history_yield(db: Session, kind: str, ref_id: int, before: datetime, limit: int) -> list[float]:
    rows = (
        db.query(TelemetrySample)
        .filter(
            TelemetrySample.kind == kind, TelemetrySample.ref_id == ref_id,
            TelemetrySample.sampled_at < before,
        )
        .order_by(TelemetrySample.sampled_at.desc())
        .limit(limit)
        .all()
    )
    return [float(row.yield_count) for row in rows]


def _notify_new(db: Session, row: AnomalyEvent) -> None:
    channel = get_value(db, "anomaly_notify_channel", "inapp")
    recipients = get_value(db, "anomaly_notify_recipients", "")
    notify_event.deliver(
        db, subject=row.title, body=row.detail, ref_type="anomaly", ref_id=row.id,
        channel=channel, recipients=recipients,
    )
    row.notified_at = datetime.now(timezone.utc)
    db.commit()


def detect_sensor_anomalies(
    db: Session,
    tenant_id: str,
    *,
    samples: list[TelemetrySample],
    now: datetime,
) -> tuple[list[AnomalyEvent], int]:
    drop_pct = max(1.0, get_float(db, "anomaly_eps_drop_pct", 50.0))
    silent_eps = max(0.0, get_float(db, "anomaly_silent_eps", 0.05))
    min_expected = max(0.0, get_float(db, "anomaly_min_expected_eps", 0.5))
    opened: list[AnomalyEvent] = []
    live: set[str] = set()
    measured: set[str] = set()
    for sample in samples:
        catalog = float(sample.expected_eps or 0)
        learned = _mean(_history_eps(db, sample.ref_id or 0, sample.sampled_at))
        expected = learned if learned > 0 else catalog
        measured.add(f"{sample.ref_id}:{sample.name}")
        if expected < min_expected:
            continue
        observed = float(sample.eps or 0)
        ratio = observed / expected if expected else 0.0
        extra = {"sample_id": sample.id, "window_minutes": sample.window_minutes, **(sample.extra or {})}
        if observed <= silent_eps:
            kind, severity = "silent_sensor", "high"
            title = f"Silent sensor: {sample.name}"
            detail = (
                f"Observed {observed:.3f} EPS over {sample.window_minutes}m against a baseline of "
                f"{expected:.3f} EPS ({int(drop_pct)}% drop threshold)."
            )
        elif ratio * 100 < drop_pct:
            kind, severity = "silent_sensor", "medium"
            title = f"EPS drop: {sample.name}"
            detail = (
                f"Observed {observed:.3f} EPS is {ratio:.0%} of the {expected:.3f} EPS baseline "
                f"(threshold {int(drop_pct)}%)."
            )
        elif learned > 0 and ratio >= 3:
            kind, severity = "eps_spike", "medium"
            title = f"EPS spike: {sample.name}"
            detail = f"Observed {observed:.3f} EPS is {ratio:.1f}× the {expected:.3f} EPS baseline."
        else:
            continue
        live.add(f"{kind}:sensor_log_source:{sample.ref_id or 0}:{sample.name}")
        row, created = _open_event(
            db, tenant_id=tenant_id, kind=kind, severity=severity, title=title, detail=detail,
            ref_type="sensor_log_source", ref_id=sample.ref_id, name=sample.name,
            observed=observed, expected=expected, extra=extra, now=now,
        )
        if created:
            opened.append(row)
    resolved = 0
    if measured:
        for kind in ("silent_sensor", "eps_spike"):
            open_rows = db.query(AnomalyEvent).filter(
                AnomalyEvent.tenant_id == tenant_id, AnomalyEvent.kind == kind, AnomalyEvent.status == "open",
            ).all()
            for row in open_rows:
                if f"{row.ref_id}:{row.name}" not in measured:
                    continue
                if row.fingerprint in live:
                    continue
                row.status = "resolved"
                row.resolved_at = now
                resolved += 1
    return opened, resolved


def detect_feed_anomalies(
    db: Session,
    tenant_id: str,
    *,
    now: datetime,
) -> tuple[list[AnomalyEvent], int]:
    drop_pct = max(1.0, get_float(db, "anomaly_feed_drop_pct", 50.0))
    baseline_runs = max(2, get_int(db, "anomaly_feed_baseline_runs", 8))
    min_baseline = max(1.0, get_float(db, "anomaly_feed_min_baseline", 2.0))
    opened: list[AnomalyEvent] = []
    live: set[str] = set()

    def consider(kind: str, source_id: int, name: str, interval_minutes: int) -> None:
        latest = (
            db.query(TelemetrySample)
            .filter(TelemetrySample.kind == kind, TelemetrySample.ref_id == source_id)
            .order_by(TelemetrySample.sampled_at.desc())
            .first()
        )
        if latest is None:
            return
        history = _history_yield(db, kind, source_id, latest.sampled_at, baseline_runs)
        expected = _mean(history)
        if expected < min_baseline:
            return
        observed = float(latest.yield_count or 0)
        ratio = observed / expected if expected else 0.0
        if observed == 0 or ratio * 100 < drop_pct:
            title = f"Feed yield collapse: {name}"
            detail = (
                f"Latest run produced {int(observed)} item(s) against a baseline of "
                f"{expected:.1f} over {len(history)} run(s) (interval {interval_minutes}m)."
            )
            live.add(f"feed_anomaly:{kind}:{source_id}:{name}")
            row, created = _open_event(
                db, tenant_id=tenant_id, kind="feed_anomaly", severity="high" if observed == 0 else "medium",
                title=title, detail=detail, ref_type=kind, ref_id=source_id, name=name,
                observed=observed, expected=expected,
                extra={"sample_id": latest.id, "runs": len(history)}, now=now,
            )
            if created:
                opened.append(row)

    for source in db.query(IntelSource).filter(IntelSource.enabled.is_(True)).all():
        consider("intel_feed", source.id, source.name, source.interval_minutes or 60)
    for source in db.query(IoCSource).filter(IoCSource.enabled.is_(True)).all():
        consider("ioc_feed", source.id, source.name, source.interval_minutes or 60)

    resolved = _resolve_missing(db, tenant_id, "feed_anomaly", live, now)
    return opened, resolved


def run_detection(
    db: Session,
    tenant_id: str,
    *,
    search_fn: SearchFn | None = None,
    now: datetime | None = None,
    notify: bool = True,
) -> dict[str, Any]:
    if not get_bool(db, "anomaly_enabled", True):
        return {"skipped": True, "reason": "disabled"}
    current = _now(now)
    samples = collect_sensor_samples(db, tenant_id, search_fn=search_fn, now=current)
    opened_sensors, resolved_sensors = detect_sensor_anomalies(db, tenant_id, samples=samples, now=current)
    opened_feeds, resolved_feeds = detect_feed_anomalies(db, tenant_id, now=current)
    db.commit()
    opened = opened_sensors + opened_feeds
    if notify:
        for row in opened:
            _notify_new(db, row)
    return {
        "sampled": len(samples),
        "opened": len(opened),
        "resolved": resolved_sensors + resolved_feeds,
        "anomalies": [serialize(row) for row in opened],
    }


def list_anomalies(db: Session, tenant_id: str, *, status: str = "open", limit: int = 100) -> list[dict]:
    query = db.query(AnomalyEvent).filter(AnomalyEvent.tenant_id == tenant_id)
    if status:
        query = query.filter(AnomalyEvent.status == status)
    rows = query.order_by(AnomalyEvent.last_seen.desc()).limit(limit).all()
    return [serialize(row) for row in rows]


def set_status(db: Session, tenant_id: str, anomaly_id: int, status: str) -> AnomalyEvent:
    row = db.query(AnomalyEvent).filter(AnomalyEvent.id == anomaly_id, AnomalyEvent.tenant_id == tenant_id).first()
    if row is None:
        raise LookupError("Anomaly not found")
    if status not in {"open", "acked", "resolved"}:
        raise ValueError("Status must be open, acked or resolved")
    row.status = status
    if status == "resolved":
        row.resolved_at = datetime.now(timezone.utc)
    elif status == "open":
        row.resolved_at = None
    db.commit()
    db.refresh(row)
    return row


def summary(db: Session, tenant_id: str) -> dict[str, Any]:
    rows = db.query(AnomalyEvent).filter(AnomalyEvent.tenant_id == tenant_id, AnomalyEvent.status == "open").all()
    by_kind: dict[str, int] = {}
    for row in rows:
        by_kind[row.kind] = by_kind.get(row.kind, 0) + 1
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    sampled = db.query(TelemetrySample).filter(
        TelemetrySample.tenant_id == tenant_id, TelemetrySample.sampled_at >= since,
    ).count()
    return {
        "open": len(rows),
        "by_kind": by_kind,
        "samples_24h": sampled,
        "items": [serialize(row) for row in sorted(rows, key=lambda item: item.last_seen or item.created_at, reverse=True)[:12]],
    }
