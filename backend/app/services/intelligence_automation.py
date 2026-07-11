"""Automated, scoped cyber-intelligence and IoC ingestion."""
from __future__ import annotations

import ipaddress
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from ..models.automation import IntelSource, IoCObservation, IoCSource
from ..models.content import IntelItem, KnowledgeItem
from ..models.entities import IoC
from . import entities, intel_collector, llm
from .settings_service import get_all_resolved

INCLUDE_TOPICS = {
    "active attack": 0.35, "actively exploited": 0.45, "threat campaign": 0.35,
    "malware": 0.25, "ransomware": 0.35, "incident response": 0.25,
    "forensic": 0.2, "threat hunting": 0.3, "detection engineering": 0.35,
    "sigma": 0.3, "yara": 0.3, "splunk": 0.25, "elastic": 0.2,
    "zeek": 0.25, "sysmon": 0.25, "windows security": 0.2,
    "linux security": 0.2, "cve-": 0.15, "zero-day": 0.35,
}
EXCLUDE_TOPICS = {
    "cloud security", "aws security", "azure security", "gcp security",
    "kubernetes security", "api security", "web3", "cryptocurrency",
}
DEFAULT_MIN_RELEVANCE = 0.55
USER_AGENT = "SOC-Workbench/1.1 (+self-hosted threat intelligence)"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_default_sources(db: Session) -> None:
    if db.query(IoCSource).count() == 0:
        db.add_all([
            IoCSource(name="ThreatFox Recent IoCs", adapter="threatfox",
                      url="https://threatfox-api.abuse.ch/api/v1/", trust_score=0.85,
                      interval_minutes=180),
            IoCSource(name="URLhaus Online URLs", adapter="urlhaus_text",
                      url="https://urlhaus.abuse.ch/downloads/text_online/", trust_score=0.85,
                      interval_minutes=60),
            IoCSource(name="CISA Known Exploited Vulnerabilities", adapter="cisa_kev",
                      url="https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
                      trust_score=0.95, interval_minutes=360),
        ])
        db.commit()


def scope_score(title: str, content: str, trust_score: float = 0.7) -> tuple[float, str]:
    text = f"{title}\n{content}".lower()
    excluded = [topic for topic in EXCLUDE_TOPICS if topic in text]
    included = [(topic, weight) for topic, weight in INCLUDE_TOPICS.items() if topic in text]
    if excluded and not included:
        return 0.0, "excluded_topic:" + ",".join(sorted(excluded))
    score = 0.15 + min(trust_score * 0.25, 0.25)
    score += min(sum(weight for _, weight in included), 0.6)
    if "critical" in text or "in the wild" in text:
        score += 0.1
    if excluded:
        score -= 0.25
    return round(max(0.0, min(score, 1.0)), 2), "matched:" + ",".join(x[0] for x in included[:6])


def _save_knowledge(db: Session, item: IntelItem) -> KnowledgeItem | None:
    existing = db.query(KnowledgeItem).filter(KnowledgeItem.url == item.url).first()
    if existing:
        return None
    row = KnowledgeItem(
        title=item.title, item_type="article", content=item.content or item.summary_en,
        summary=item.summary_en, category=item.category, tags=item.tags or [],
        source=item.source, url=item.url,
        notes=f"Auto-ingested; relevance={item.relevance:.2f}",
    )
    db.add(row)
    return row


def _normalize_ioc(value: str, ioc_type: str) -> str | None:
    value = value.strip().strip("[](){}<>.,;'\"")
    if not value:
        return None
    if ioc_type == "ipv4":
        try:
            ip = ipaddress.ip_address(value)
            if not isinstance(ip, ipaddress.IPv4Address) or not ip.is_global:
                return None
            return str(ip)
        except ValueError:
            return None
    if ioc_type == "domain":
        domain = value.lower().rstrip(".")
        if domain in {"example.com", "localhost"} or "." not in domain:
            return None
        return domain
    if ioc_type == "url":
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
    return value


def store_ioc(db: Session, value: str, ioc_type: str, source: str,
              confidence_score: float = 0.6, raw: dict | None = None,
              first_seen: str = "", last_seen: str = "", external_id: str = "",
              tags: list[str] | None = None, malware: str = "") -> IoC | None:
    normalized = _normalize_ioc(value, ioc_type)
    if not normalized:
        return None
    row = db.query(IoC).filter(IoC.value == normalized).first()
    if not row:
        label = "high" if confidence_score >= 0.8 else "medium" if confidence_score >= 0.5 else "low"
        row = IoC(value=normalized, ioc_type=ioc_type, source=source,
                  confidence=label, severity="medium", tags=tags or [],
                  related_malware=malware, first_seen=first_seen, last_seen=last_seen)
        db.add(row)
        db.flush()
    seen = db.query(IoCObservation).filter(
        IoCObservation.ioc_id == row.id, IoCObservation.source_name == source,
        IoCObservation.external_id == external_id,
    ).first()
    if not seen:
        db.add(IoCObservation(
            ioc_id=row.id, source_name=source, external_id=external_id,
            first_seen=first_seen, last_seen=last_seen,
            confidence_score=confidence_score, raw_payload=raw or {},
        ))
    return row


def _extract_item_iocs(db: Session, item: IntelItem) -> int:
    buckets = entities.extract_iocs(f"{item.title}\n{item.content}")
    mapping = {"ips": "ipv4", "domains": "domain", "urls": "url",
               "emails": "email", "hashes": "hash"}
    count = 0
    for bucket, ioc_type in mapping.items():
        for value in buckets.get(bucket, []):
            if store_ioc(db, value, ioc_type, item.source,
                         confidence_score=max(0.4, item.relevance),
                         raw={"intel_url": item.url}, tags=item.tags):
                count += 1
    return count


def collect_intel_source(db: Session, source: IntelSource) -> dict:
    source.last_run_at = utcnow()
    try:
        collected = intel_collector.collect_feed(source.url, limit=50)
        new_count = kb_count = ioc_count = rejected = 0
        cfg = llm.config_from_settings(get_all_resolved(db)) if source.summarize else None
        for incoming in collected:
            if db.query(IntelItem).filter(IntelItem.content_hash == incoming.content_hash).first():
                continue
            score, reason = scope_score(incoming.title, incoming.content, source.trust_score)
            if score < DEFAULT_MIN_RELEVANCE:
                rejected += 1
                continue
            incoming.relevance = score
            if cfg and cfg.has_credentials:
                try:
                    result = llm.complete(
                        "You are a senior SOC analyst. Return a concise factual English summary, "
                        "SOC impact, and actions. Do not invent facts.",
                        incoming.content[:8000], cfg,
                    )
                    incoming.summary_en = result.text
                except llm.LLMError:
                    pass
            row = IntelItem(
                title=incoming.title, original_title=incoming.original_title,
                source=source.name, url=incoming.url, published_at=incoming.published_at,
                content=incoming.content, category=incoming.category,
                tags=incoming.tags, entities=incoming.entities,
                summary_en=incoming.summary_en, summary_fa=incoming.summary_fa,
                relevance=score, content_hash=incoming.content_hash,
                notes=reason,
            )
            db.add(row)
            db.flush()
            new_count += 1
            if source.auto_save_kb and _save_knowledge(db, row):
                kb_count += 1
            if source.auto_extract_iocs:
                ioc_count += _extract_item_iocs(db, row)
        source.last_success_at = utcnow()
        source.last_error = ""
        source.failure_count = 0
        db.commit()
        return {"new": new_count, "knowledge": kb_count, "iocs": ioc_count, "rejected": rejected}
    except Exception as exc:
        source.failure_count += 1
        source.last_error = str(exc)[:1000]
        db.commit()
        raise


def _threatfox(client: httpx.Client, source: IoCSource) -> list[dict]:
    response = client.post(source.url, json={"query": "get_iocs", "days": 3})
    response.raise_for_status()
    data = response.json().get("data") or []
    return [{
        "value": x.get("ioc", ""), "type": {
            "ip:port": "custom", "domain": "domain", "url": "url",
            "md5_hash": "hash", "sha1_hash": "hash", "sha256_hash": "hash",
        }.get(x.get("ioc_type", ""), "custom"),
        "external_id": x.get("id", ""), "first_seen": x.get("first_seen_utc", ""),
        "last_seen": x.get("last_seen_utc", ""), "malware": x.get("malware_printable", ""),
        "tags": x.get("tags") or [], "raw": x,
    } for x in data]


def _urlhaus_text(client: httpx.Client, source: IoCSource) -> list[dict]:
    response = client.get(source.url)
    response.raise_for_status()
    return [{"value": line.strip(), "type": "url", "raw": {}}
            for line in response.text.splitlines()
            if line.strip() and not line.startswith("#")]


def _cisa_kev(client: httpx.Client, source: IoCSource) -> list[dict]:
    response = client.get(source.url)
    response.raise_for_status()
    # KEV entries are vulnerability intelligence, stored as custom observables.
    return [{
        "value": x.get("cveID", ""), "type": "custom", "external_id": x.get("cveID", ""),
        "first_seen": x.get("dateAdded", ""), "tags": ["cisa-kev", x.get("vendorProject", "")],
        "malware": "", "raw": x,
    } for x in response.json().get("vulnerabilities", [])]


ADAPTERS = {"threatfox": _threatfox, "urlhaus_text": _urlhaus_text, "cisa_kev": _cisa_kev}


def collect_ioc_source(db: Session, source: IoCSource) -> dict:
    source.last_run_at = utcnow()
    adapter = ADAPTERS.get(source.adapter)
    if not adapter:
        raise ValueError(f"Unknown IoC adapter: {source.adapter}")
    try:
        with httpx.Client(timeout=45, follow_redirects=True,
                          headers={"User-Agent": USER_AGENT}) as client:
            records = adapter(client, source)
        accepted = 0
        for record in records:
            if store_ioc(
                db, record.get("value", ""), record.get("type", "custom"), source.name,
                confidence_score=source.trust_score, raw=record.get("raw"),
                first_seen=record.get("first_seen", ""), last_seen=record.get("last_seen", ""),
                external_id=str(record.get("external_id", "")),
                tags=[x for x in record.get("tags", []) if x],
                malware=record.get("malware", ""),
            ):
                accepted += 1
        source.last_success_at = utcnow()
        source.last_error = ""
        source.failure_count = 0
        db.commit()
        return {"received": len(records), "accepted": accepted}
    except Exception as exc:
        source.failure_count += 1
        source.last_error = str(exc)[:1000]
        db.commit()
        raise


def run_all(db: Session) -> dict:
    seed_default_sources(db)
    result = {"intel": {}, "iocs": {}}
    for source in db.query(IntelSource).filter(IntelSource.enabled.is_(True)).all():
        try:
            result["intel"][source.name] = collect_intel_source(db, source)
        except Exception as exc:
            result["intel"][source.name] = {"error": str(exc)}
    for source in db.query(IoCSource).filter(IoCSource.enabled.is_(True)).all():
        try:
            result["iocs"][source.name] = collect_ioc_source(db, source)
        except Exception as exc:
            result["iocs"][source.name] = {"error": str(exc)}
    return result
