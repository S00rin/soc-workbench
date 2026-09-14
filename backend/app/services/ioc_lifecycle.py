"""IoC lifecycle: decay scoring, expiry, Splunk retro-hunt sightings, watchlist export."""
from __future__ import annotations

import csv
import io
import json
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..logging_config import get_logger
from ..models.automation import IoCObservation
from ..models.entities import IoC
from ..models.ops import IoCSighting
from .settings_service import get_all_resolved, get_bool, get_float, get_int, get_value
from .splunk_client import SplunkError, client_from_settings

logger = get_logger(__name__)

SearchFn = Callable[..., dict]
SEVERITY_WEIGHT = {"critical": 1.25, "high": 1.0, "medium": 0.8, "low": 0.55}
CONFIDENCE_WEIGHT = {"high": 1.1, "medium": 1.0, "low": 0.75}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _aware(value)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return _aware(datetime.fromisoformat(normalized))
    except ValueError:
        try:
            return datetime.strptime(normalized[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                return datetime.fromtimestamp(float(normalized), tz=timezone.utc)
            except (OSError, ValueError):
                return None


def _now(value: datetime | None) -> datetime:
    return (_aware(value) or datetime.now(timezone.utc)).astimezone(timezone.utc)


def _escape_spl(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def last_activity(ioc: IoC) -> datetime | None:
    return (
        _parse_ts(ioc.last_sighted_at)
        or _parse_ts(ioc.last_seen)
        or _parse_ts(ioc.first_seen)
        or _aware(ioc.created_at)
    )


def score_indicator(
    ioc: IoC,
    *,
    now: datetime,
    half_life_days: float,
    expire_score: float,
    observations: list[IoCObservation] | None = None,
) -> tuple[float, str]:
    if ioc.false_positive:
        return 0.0, "retired"
    expires = _parse_ts(ioc.expires_at)
    if expires and expires < now:
        return 0.0, "expired"

    last = last_activity(ioc)
    age_days = max(0.0, (now - last).total_seconds() / 86400) if last else 0.0
    decay = 0.5 ** (age_days / max(0.5, half_life_days))
    trusts = [obs.confidence_score for obs in (observations or []) if obs.confidence_score]
    trust = max(trusts) if trusts else 0.7
    sighting_boost = min(1.6, 1.0 + 0.08 * int(ioc.sighting_count or 0))
    severity = SEVERITY_WEIGHT.get((ioc.severity or "medium").lower(), 0.8)
    confidence = CONFIDENCE_WEIGHT.get((ioc.confidence or "medium").lower(), 1.0)
    score = 100.0 * decay * min(1.25, trust / 0.7) * sighting_boost * severity * confidence
    score = round(max(0.0, min(100.0, score)), 1)
    if score < expire_score:
        return score, "expired"
    if score < 40:
        return score, "decaying"
    if ioc.watchlist:
        return score, "watchlist"
    return score, "active"


def refresh_scores(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    current = _now(now)
    half_life = max(0.5, get_float(db, "ioc_decay_half_life_days", 14.0))
    expire_score = max(0.0, get_float(db, "ioc_expire_score", 15.0))
    watchlist_min = get_float(db, "ioc_watchlist_min_score", 60.0)
    observations: dict[int, list[IoCObservation]] = {}
    for obs in db.query(IoCObservation).all():
        observations.setdefault(obs.ioc_id, []).append(obs)
    counts = {"active": 0, "watchlist": 0, "decaying": 0, "expired": 0, "retired": 0, "promoted": 0}
    for ioc in db.query(IoC).all():
        score, status = score_indicator(
            ioc, now=current, half_life_days=half_life, expire_score=expire_score,
            observations=observations.get(ioc.id, []),
        )
        ioc.score = score
        if status == "expired" and not ioc.expires_at:
            ioc.expires_at = current.isoformat()
        if (
            not ioc.false_positive
            and status not in {"expired", "retired"}
            and score >= watchlist_min
            and not ioc.watchlist
        ):
            ioc.watchlist = True
            status = "watchlist"
            counts["promoted"] += 1
        if ioc.watchlist and status not in {"expired", "retired"}:
            status = "watchlist"
        ioc.status = status
        counts[status] = counts.get(status, 0) + 1
    db.commit()
    return counts


def stix_pattern(ioc: IoC) -> str:
    value = (ioc.value or "").replace("\\", "\\\\").replace("'", "\\'")
    kind = (ioc.ioc_type or "custom").lower()
    if kind in {"ipv4", "ip"}:
        return f"[ipv4-addr:value = '{value}']"
    if kind == "ipv6":
        return f"[ipv6-addr:value = '{value}']"
    if kind == "domain":
        return f"[domain-name:value = '{value}']"
    if kind == "url":
        return f"[url:value = '{value}']"
    if kind == "email":
        return f"[email-addr:value = '{value}']"
    if kind == "hash":
        algo = {32: "MD5", 40: "SHA-1", 64: "SHA-256"}.get(len(ioc.value or ""), "SHA-256")
        return f"[file:hashes.'{algo}' = '{value}']"
    return f"[x-opencti-custom-object:value = '{value}']"


def watchlist_query(db: Session, *, scope: str = "watchlist") -> list[IoC]:
    query = db.query(IoC).filter(IoC.false_positive.is_(False), IoC.status.notin_(["expired", "retired"]))
    if scope == "watchlist":
        query = query.filter(IoC.watchlist.is_(True))
    elif scope == "active":
        query = query.filter(IoC.status.in_(["active", "watchlist", "decaying"]))
    return query.order_by(IoC.score.desc(), IoC.created_at.desc()).all()


def export_csv(iocs: list[IoC]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "value", "type", "severity", "confidence", "score", "status", "watchlist",
        "source", "tags", "first_seen", "last_seen", "last_sighted_at", "sighting_count", "expires_at",
    ])
    for ioc in iocs:
        writer.writerow([
            ioc.value, ioc.ioc_type, ioc.severity, ioc.confidence, ioc.score, ioc.status,
            "true" if ioc.watchlist else "false", ioc.source,
            ",".join(ioc.tags or []), ioc.first_seen, ioc.last_seen, ioc.last_sighted_at,
            ioc.sighting_count, ioc.expires_at,
        ])
    return buf.getvalue()


def export_stix(iocs: list[IoC], *, now: datetime | None = None) -> dict[str, Any]:
    current = _now(now)
    created = current.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    objects = []
    for ioc in iocs:
        valid_from = (_parse_ts(ioc.first_seen) or _aware(ioc.created_at) or current).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        objects.append({
            "type": "indicator",
            "spec_version": "2.1",
            "id": f"indicator--{uuid.uuid5(uuid.NAMESPACE_URL, f'soc-workbench:{ioc.id}:{ioc.value}')}",
            "created": valid_from,
            "modified": created,
            "name": ioc.value,
            "description": ioc.notes or f"SOC Workbench IoC from {ioc.source or 'unknown'}",
            "indicator_types": ["malicious-activity"],
            "pattern": stix_pattern(ioc),
            "pattern_type": "stix",
            "valid_from": valid_from,
            "confidence": max(0, min(100, int(round(ioc.score or 0)))),
            "labels": list(ioc.tags or []) + ([ioc.severity] if ioc.severity else []),
        })
    return {
        "type": "bundle",
        "id": f"bundle--{uuid.uuid4()}",
        "objects": objects,
    }


def _row_blob(row: dict) -> str:
    try:
        return json.dumps(row, default=str).lower()
    except TypeError:
        return str(row).lower()


def retro_hunt(
    db: Session,
    *,
    search_fn: SearchFn | None = None,
    earliest: str | None = None,
    max_iocs: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    earliest = earliest or get_value(db, "ioc_retrohunt_earliest", "-24h")
    limit = max_iocs or max(1, get_int(db, "ioc_retrohunt_max_iocs", 50))
    if search_fn is None:
        client = client_from_settings(get_all_resolved(db))
        if client is None:
            return {"skipped": True, "reason": "splunk_unconfigured", "hunted": 0, "sighted": 0}
        def search_fn(spl: str, earliest: str = "", latest: str = "now", **_: Any) -> dict:  # noqa: ARG001
            return client.search(spl, earliest=earliest, latest=latest)

    candidates = (
        db.query(IoC)
        .filter(IoC.false_positive.is_(False), IoC.status.notin_(["expired", "retired"]))
        .order_by(IoC.score.desc(), IoC.created_at.desc())
        .limit(limit)
        .all()
    )
    sighted = 0
    searched = 0
    errors: list[str] = []
    chunk_size = 15
    for offset in range(0, len(candidates), chunk_size):
        chunk = candidates[offset:offset + chunk_size]
        clause = " OR ".join(f'"{_escape_spl(ioc.value)}"' for ioc in chunk if ioc.value)
        if not clause:
            continue
        spl = f"search {clause}"
        searched += len(chunk)
        try:
            payload = search_fn(spl, earliest=earliest, latest="now", max_results=1000)
        except (SplunkError, Exception) as exc:  # noqa: BLE001
            errors.append(str(exc)[:200])
            logger.warning("Retro-hunt search failed: %s", exc)
            continue
        rows = payload.get("results") or []
        for ioc in chunk:
            needle = (ioc.value or "").lower()
            if not needle:
                continue
            hits = [row for row in rows if needle in _row_blob(row)]
            if not hits:
                continue
            times = [_parse_ts(row.get("_time") or row.get("time")) for row in hits]
            times = [item for item in times if item]
            first = min(times).isoformat() if times else current.isoformat()
            last = max(times).isoformat() if times else current.isoformat()
            db.add(IoCSighting(
                ioc_id=ioc.id, source="splunk", count=len(hits), query=spl,
                observed_at=current.isoformat(), first_seen=first, last_seen=last,
                raw={"hit_count": len(hits), "earliest": earliest},
            ))
            ioc.sighting_count = int(ioc.sighting_count or 0) + 1
            ioc.last_sighted_at = last
            ioc.last_seen = last
            if not ioc.first_seen:
                ioc.first_seen = first
            sighted += 1
    db.commit()
    scores = refresh_scores(db, now=current)
    return {
        "hunted": searched, "sighted": sighted, "errors": errors[:5],
        "scores": scores, "earliest": earliest,
    }


def run_lifecycle(db: Session, *, hunt: bool | None = None, search_fn: SearchFn | None = None, now: datetime | None = None) -> dict[str, Any]:
    scores = refresh_scores(db, now=now)
    result: dict[str, Any] = {"scores": scores, "hunt": None}
    do_hunt = get_bool(db, "ioc_retrohunt_enabled", False) if hunt is None else hunt
    if do_hunt:
        result["hunt"] = retro_hunt(db, search_fn=search_fn, now=now)
    return result


def serialize_sighting(row: IoCSighting) -> dict[str, Any]:
    return {
        "id": row.id, "ioc_id": row.ioc_id, "source": row.source, "count": row.count,
        "query": row.query, "observed_at": row.observed_at, "first_seen": row.first_seen,
        "last_seen": row.last_seen,
    }
