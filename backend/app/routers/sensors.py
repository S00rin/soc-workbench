"""Equipment & Sensor Library API (Module 17).

Read access follows module RBAC (handled by the access middleware); mutations
require the administrator role. Sensor documentation can be published to
Confluence through an existing, Confluence-enabled Atlassian connection.
"""
from __future__ import annotations

import io
import json
import re
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.sensors import Sensor, SensorDocument, SensorLogSource
from ..security import AuthContext, get_auth_context, require_admin
from ..services import sensors as svc
from ..services.atlassian_connections import scoped_connection
from ..services.atlassian_http import AtlassianError, AtlassianTransport
from ..services.confluence_provider import ConfluenceProvider
from ..services.integration_history import audit, correlation_id, record_history

router = APIRouter(prefix="/api/sensors", tags=["sensors"])

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
    return slug or "sensor"


# --- schemas -------------------------------------------------------------

class Capability(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    category: str = Field(default="", max_length=40)
    description: str = Field(default="", max_length=600)


class SensorIn(BaseModel):
    slug: str = Field(default="", max_length=160)
    name: str = Field(min_length=1, max_length=200)
    vendor: str = Field(default="", max_length=160)
    product_model: str = Field(default="", max_length=160)
    category: str = Field(default="other", max_length=40)
    description: str = ""
    capabilities: list[Capability] = Field(default_factory=list)
    deployment_notes: str = ""
    log_format: str = Field(default="syslog", max_length=40)
    collection_methods: list[str] = Field(default_factory=list)
    status: str = Field(default="active", max_length=20)
    criticality: str = Field(default="medium", max_length=20)
    environment: str = Field(default="all", max_length=20)
    vendor_url: str = Field(default="", max_length=400)
    doc_url: str = Field(default="", max_length=400)
    tags: list[str] = Field(default_factory=list)
    mitre_tactics: list[str] = Field(default_factory=list)
    owner: str = Field(default="", max_length=160)


class LogSourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    log_type: str = Field(default="", max_length=120)
    format: str = Field(default="syslog", max_length=40)
    sample: str = ""
    key_fields: list[str] = Field(default_factory=list)
    siem_sourcetype: str = Field(default="", max_length=160)
    siem_index: str = Field(default="", max_length=160)
    mitre_data_source: str = Field(default="", max_length=160)
    eps_estimate: int = Field(default=0, ge=0)
    retention_days: int = Field(default=0, ge=0)
    order_index: int = 0


class DocumentIn(BaseModel):
    kind: str = Field(default="reference", max_length=30)
    title: str = Field(min_length=1, max_length=240)
    summary: str = Field(default="", max_length=400)
    content: str = ""
    severity: str = Field(default="", max_length=20)
    trigger: str = ""
    mitre_techniques: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    order_index: int = 0


class PublishIn(BaseModel):
    connection_id: int
    space: str = Field(min_length=1, max_length=160)  # cloud: numeric space id; DC: space key
    parent_page_id: str = Field(default="", max_length=120)
    document_id: int | None = None  # publish one document; omit for the full sensor profile


def _validate_enums(payload: SensorIn) -> None:
    if payload.category not in svc.CATEGORIES:
        raise HTTPException(422, f"Unknown category: {payload.category}")
    if payload.status not in svc.STATUSES:
        raise HTTPException(422, f"Unknown status: {payload.status}")
    if payload.criticality not in svc.CRITICALITIES:
        raise HTTPException(422, f"Unknown criticality: {payload.criticality}")
    if payload.environment not in svc.ENVIRONMENTS:
        raise HTTPException(422, f"Unknown environment: {payload.environment}")
    bad = [m for m in payload.collection_methods if m not in svc.COLLECTION_METHODS]
    if bad:
        raise HTTPException(422, f"Unknown collection methods: {', '.join(bad)}")


def _get_sensor(db: Session, context: AuthContext, sensor_id: int) -> Sensor:
    row = db.query(Sensor).filter(Sensor.id == sensor_id, Sensor.tenant_id == context.tenant_id).first()
    if row is None:
        raise HTTPException(404, "Sensor not found")
    return row


def _get_document(db: Session, context: AuthContext, document_id: int) -> SensorDocument:
    row = (
        db.query(SensorDocument)
        .join(Sensor, Sensor.id == SensorDocument.sensor_id)
        .filter(SensorDocument.id == document_id, Sensor.tenant_id == context.tenant_id)
        .first()
    )
    if row is None:
        raise HTTPException(404, "Document not found")
    return row


def _get_log_source(db: Session, context: AuthContext, ls_id: int) -> SensorLogSource:
    row = (
        db.query(SensorLogSource)
        .join(Sensor, Sensor.id == SensorLogSource.sensor_id)
        .filter(SensorLogSource.id == ls_id, Sensor.tenant_id == context.tenant_id)
        .first()
    )
    if row is None:
        raise HTTPException(404, "Log source not found")
    return row


# --- metadata ------------------------------------------------------------

@router.get("/catalog")
def catalog(_: AuthContext = Depends(get_auth_context)):
    return svc.catalog()


@router.get("/summary")
def summary(db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    rows = db.query(Sensor).filter(Sensor.tenant_id == context.tenant_id).all()
    return svc.coverage_summary(rows)


# --- sensors -------------------------------------------------------------

@router.get("")
def list_sensors(
    category: str = "", status: str = "", criticality: str = "", tag: str = "",
    q: str = Query(default="", max_length=200),
    db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context),
):
    query = db.query(Sensor).filter(Sensor.tenant_id == context.tenant_id)
    if category:
        query = query.filter(Sensor.category == category)
    if status:
        query = query.filter(Sensor.status == status)
    if criticality:
        query = query.filter(Sensor.criticality == criticality)
    if q:
        pattern = f"%{q}%"
        query = query.filter(or_(Sensor.name.ilike(pattern), Sensor.vendor.ilike(pattern), Sensor.slug.ilike(pattern)))
    rows = query.order_by(Sensor.category, Sensor.name).all()
    if tag:
        rows = [row for row in rows if tag in (row.tags or [])]
    return {"items": [svc.sensor_summary(row) for row in rows], "total": len(rows)}


@router.get("/{sensor_id}")
def get_sensor(sensor_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    return svc.sensor_detail(_get_sensor(db, context, sensor_id))


@router.post("")
def create_sensor(payload: SensorIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    _validate_enums(payload)
    slug = _slugify(payload.slug or payload.name)
    if db.query(Sensor).filter(Sensor.tenant_id == context.tenant_id, Sensor.slug == slug).first():
        raise HTTPException(409, f"A sensor with slug '{slug}' already exists")
    data = payload.model_dump()
    data["slug"] = slug
    data["capabilities"] = [c.model_dump() if hasattr(c, "model_dump") else c for c in payload.capabilities]
    row = Sensor(tenant_id=context.tenant_id, updated_by=context.username, **data)
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, context, "sensor.create", "sensor", str(row.id))
    return svc.sensor_detail(row)


@router.put("/{sensor_id}")
def update_sensor(sensor_id: int, payload: SensorIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    row = _get_sensor(db, context, sensor_id)
    _validate_enums(payload)
    data = payload.model_dump()
    data["capabilities"] = [c.model_dump() if hasattr(c, "model_dump") else c for c in payload.capabilities]
    new_slug = _slugify(payload.slug or payload.name)
    if new_slug != row.slug and db.query(Sensor).filter(Sensor.tenant_id == context.tenant_id, Sensor.slug == new_slug).first():
        raise HTTPException(409, f"A sensor with slug '{new_slug}' already exists")
    data["slug"] = new_slug
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_by = context.username
    db.commit()
    db.refresh(row)
    audit(db, context, "sensor.update", "sensor", str(row.id))
    return svc.sensor_detail(row)


@router.delete("/{sensor_id}")
def delete_sensor(sensor_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    row = _get_sensor(db, context, sensor_id)
    db.delete(row)
    db.commit()
    audit(db, context, "sensor.delete", "sensor", str(sensor_id))
    return {"ok": True}


# --- log sources ---------------------------------------------------------

@router.post("/{sensor_id}/log-sources")
def create_log_source(sensor_id: int, payload: LogSourceIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    _get_sensor(db, context, sensor_id)
    row = SensorLogSource(sensor_id=sensor_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, context, "sensor.log_source.create", "log_source", str(row.id))
    return svc.log_source_out(row)


@router.put("/log-sources/{ls_id}")
def update_log_source(ls_id: int, payload: LogSourceIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    row = _get_log_source(db, context, ls_id)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    audit(db, context, "sensor.log_source.update", "log_source", str(row.id))
    return svc.log_source_out(row)


@router.delete("/log-sources/{ls_id}")
def delete_log_source(ls_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    row = _get_log_source(db, context, ls_id)
    db.delete(row)
    db.commit()
    audit(db, context, "sensor.log_source.delete", "log_source", str(ls_id))
    return {"ok": True}


# --- documents -----------------------------------------------------------

def _validate_doc(payload: DocumentIn) -> None:
    if payload.kind not in svc.DOC_KINDS:
        raise HTTPException(422, f"Unknown document kind: {payload.kind}")


@router.post("/{sensor_id}/documents")
def create_document(sensor_id: int, payload: DocumentIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    _get_sensor(db, context, sensor_id)
    _validate_doc(payload)
    row = SensorDocument(sensor_id=sensor_id, updated_by=context.username, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, context, "sensor.document.create", "document", str(row.id))
    return svc.document_out(row)


@router.put("/documents/{document_id}")
def update_document(document_id: int, payload: DocumentIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    row = _get_document(db, context, document_id)
    _validate_doc(payload)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.updated_by = context.username
    db.commit()
    db.refresh(row)
    audit(db, context, "sensor.document.update", "document", str(row.id))
    return svc.document_out(row)


@router.delete("/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    row = _get_document(db, context, document_id)
    db.delete(row)
    db.commit()
    audit(db, context, "sensor.document.delete", "document", str(document_id))
    return {"ok": True}


# --- export --------------------------------------------------------------

@router.get("/{sensor_id}/export/markdown")
def export_markdown(sensor_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    row = _get_sensor(db, context, sensor_id)
    body = svc.sensor_to_markdown(row).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(body), media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={row.slug}.md"},
    )


@router.get("/{sensor_id}/export/json")
def export_json(sensor_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    row = _get_sensor(db, context, sensor_id)
    body = json.dumps(svc.sensor_detail(row), ensure_ascii=False, default=str, indent=2).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(body), media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={row.slug}.json"},
    )


# --- confluence publishing ----------------------------------------------

@router.get("/publish/targets")
def publish_targets(db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    """Confluence-enabled connections the current tenant can publish to."""
    from ..models.atlassian import AtlassianConnection

    rows = db.query(AtlassianConnection).filter(
        AtlassianConnection.tenant_id == context.tenant_id,
        AtlassianConnection.enabled.is_(True),
    ).order_by(AtlassianConnection.name).all()
    return [
        {"id": row.id, "name": row.name, "deployment_type": row.deployment_type}
        for row in rows if "confluence" in (row.products or [])
    ]


@router.get("/publish/{connection_id}/spaces")
def publish_spaces(connection_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    try:
        connection = scoped_connection(db, context, connection_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    if "confluence" not in (connection.products or []):
        raise HTTPException(422, "Confluence is not enabled on this connection")
    transport = AtlassianTransport(db, connection, "confluence")
    provider = ConfluenceProvider(transport, connection.deployment_type == "cloud")
    try:
        spaces = provider.list_spaces(100)
    except AtlassianError as error:
        raise HTTPException(error.status_code if 400 <= error.status_code < 500 else 502, error.as_dict()) from error
    finally:
        transport.close()
    return [
        {"id": str(item.get("id", "")), "key": item.get("key", ""), "name": item.get("name", "")}
        for item in spaces
    ]


@router.post("/{sensor_id}/publish")
def publish_sensor(sensor_id: int, payload: PublishIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    sensor = _get_sensor(db, context, sensor_id)
    document: SensorDocument | None = None
    if payload.document_id is not None:
        document = next((d for d in sensor.documents if d.id == payload.document_id), None)
        if document is None:
            raise HTTPException(404, "Document not found for this sensor")

    try:
        connection = scoped_connection(db, context, payload.connection_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    if "confluence" not in (connection.products or []):
        raise HTTPException(422, "Confluence is not enabled on this connection")

    title = svc.confluence_title(sensor, document)
    markdown = svc.document_to_markdown(document) if document else svc.sensor_to_markdown(sensor)
    storage = svc.markdown_to_storage(markdown)
    target = document if document else sensor

    trace = correlation_id()
    started = time.perf_counter()
    transport = AtlassianTransport(db, connection, "confluence")
    provider = ConfluenceProvider(transport, connection.deployment_type == "cloud")
    try:
        page_id = target.confluence_page_id
        existing = provider.get_page(page_id) if page_id else provider.find_page(payload.space, title)
        if existing:
            page_id = str(existing.get("id", page_id))
            version = (existing.get("version") or {}).get("number", 0)
            result = provider.update_page(page_id, title, storage, version)
            action = "updated"
        else:
            result = provider.create_page(payload.space, title, storage, payload.parent_page_id)
            page_id = str(result.get("id", ""))
            action = "created"
    except AtlassianError as error:
        record_history(
            db, context, connection_id=connection.id, product="confluence",
            operation_type="page_publish", query_type="page", target_keys=[sensor.slug],
            status="failed", duration_ms=int((time.perf_counter() - started) * 1000),
            error_code=error.code, error_summary=error.message, trace_id=trace,
        )
        audit(db, context, "sensor.publish", "sensor", str(sensor.id), status="failed", trace_id=trace, details=error.as_dict())
        raise HTTPException(error.status_code if 400 <= error.status_code < 500 else 502, error.as_dict()) from error
    finally:
        transport.close()

    base = connection.base_url.rstrip("/")
    links = (result.get("_links") or {})
    webui = links.get("webui") or ""
    if webui:
        page_url = webui if webui.startswith("http") else f"{base}{'/wiki' if connection.deployment_type == 'cloud' and not webui.startswith('/wiki') else ''}{webui}"
    else:
        page_url = f"{base}{'/wiki' if connection.deployment_type == 'cloud' else ''}/pages/viewpage.action?pageId={page_id}"

    target.confluence_page_id = page_id
    target.confluence_url = page_url[:500]
    target.confluence_synced_at = datetime.now(timezone.utc)
    db.commit()

    record_history(
        db, context, connection_id=connection.id, product="confluence",
        operation_type="page_publish", query_type="page", target_keys=[sensor.slug],
        result_summary=f"Page {action}: {title}", status="success",
        duration_ms=int((time.perf_counter() - started) * 1000), result_count=1, trace_id=trace,
        metadata={"page_id": page_id, "action": action, "document_id": payload.document_id},
    )
    audit(db, context, "sensor.publish", "sensor", str(sensor.id), trace_id=trace, details={"page_id": page_id, "action": action})
    return {"ok": True, "action": action, "page_id": page_id, "url": page_url, "title": title, "correlation_id": trace}
