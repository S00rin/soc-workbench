"""Tenant-scoped Atlassian connections, mappings, history and comments."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import time
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.atlassian import (
    AtlassianConnection, AtlassianContentLink, AtlassianFieldMapping, BulkOperation, BulkOperationItem,
    IdempotencyRecord, IntegrationHistory,
)
from ..security import AuthContext, get_auth_context, require_admin
from ..services import llm
from ..services.sorin_comments import generate_comment, is_similar_comment
from ..services import bulk_operations
from ..services.atlassian_connections import (
    create_or_update, oauth_authorization_url, oauth_callback, safe_connection, scoped_connection,
)
from ..services.atlassian_http import AtlassianError, AtlassianTransport
from ..services.confluence_provider import ConfluenceProvider
from ..services.field_mapping import (
    INTERNAL_FIELDS, metadata_version, preview_mapping, resolve_mappings, validate_definition,
)
from ..services.integration_history import audit, correlation_id, record_history
from ..services.jira_kpis import (
    REPORT_TEMPLATES, calculate_soc_kpis, render_markdown_report,
    render_template_jql, report_template,
)
from ..services.jira_provider import JiraProvider, adf_to_text
from ..services.settings_service import get_all_resolved

router = APIRouter(prefix="/api/atlassian", tags=["atlassian"])


class ConnectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    products: list[Literal["jira", "confluence"]] = Field(default_factory=lambda: ["jira"])
    deployment_type: Literal["cloud", "data_center"] = "cloud"
    auth_type: Literal["api_token", "pat", "basic", "oauth2"] = "api_token"
    base_url: str
    cloud_id: str = ""
    username: str = ""
    credentials: dict[str, str] = Field(default_factory=dict)
    scopes: list[str] = Field(default_factory=list)
    verify_ssl: bool = True
    timeout: int = Field(default=30, ge=5, le=180)
    enabled: bool = True
    sorin_enabled: bool = True
    auto_post_enabled: bool = False
    bulk_auto_post_enabled: bool = False


class MappingIn(BaseModel):
    product: Literal["jira", "confluence"] = "jira"
    scope_type: Literal["connection", "project", "issue_type"] = "connection"
    project_key: str = Field(default="", max_length=80)
    issue_type_id: str = Field(default="", max_length=80)
    internal_field: str = Field(min_length=1, max_length=160)
    internal_type: str = "string"
    external_field_id: str = Field(min_length=1, max_length=160)
    external_field_name: str = ""
    external_type: str = "string"
    external_schema: dict = Field(default_factory=dict)
    transformation: dict = Field(default_factory=lambda: {"op": "identity"})
    required: bool = False
    read_only: bool = False


class MappingPreviewIn(BaseModel):
    project_key: str = ""
    issue_type_id: str = ""
    source: dict


class JiraSearchIn(BaseModel):
    jql: str = Field(min_length=1, max_length=10000)
    max_results: int = Field(default=50, ge=1, le=500)


class JiraKPIIn(JiraSearchIn):
    sla_target_hours: float = Field(default=24, gt=0, le=8760)
    acknowledgement_field: str = Field(default="", pattern=r"^[A-Za-z0-9_.-]*$", max_length=160)
    detection_field: str = Field(default="", pattern=r"^[A-Za-z0-9_.-]*$", max_length=160)


class JiraReportIn(BaseModel):
    template_id: str = Field(min_length=1, max_length=80)
    project_key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,39}$")
    max_results: int = Field(default=500, ge=1, le=500)
    sla_target_hours: float = Field(default=24, gt=0, le=8760)
    acknowledgement_field: str = Field(default="", pattern=r"^[A-Za-z0-9_.-]*$", max_length=160)
    detection_field: str = Field(default="", pattern=r"^[A-Za-z0-9_.-]*$", max_length=160)


class CommentPreviewIn(BaseModel):
    instruction: str = Field(default="Provide a factual follow-up.", max_length=10000)
    language: Literal["fa", "en"] = "fa"
    tone: Literal["formal", "technical", "concise", "executive", "follow_up", "incident_response"] = "formal"


class CommentPostIn(BaseModel):
    text: str = Field(min_length=1, max_length=30000)
    approved: bool = False
    mode: Literal["suggest_only", "require_approval", "auto_post"] = "require_approval"
    idempotency_key: str = Field(min_length=8, max_length=120)
    language: Literal["fa", "en"] = "fa"
    tone: str = "formal"


class ConfluenceSearchIn(BaseModel):
    cql: str = Field(min_length=1, max_length=10000)
    limit: int = Field(default=50, ge=1, le=100)


class ContentLinkIn(BaseModel):
    jira_issue_key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*-\d+$", max_length=80)
    confluence_page_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=120)
    relation_type: Literal["related", "runbook", "evidence", "postmortem"] = "related"


class BulkIn(BaseModel):
    product: Literal["jira", "confluence"] = "jira"
    target_type: Literal["issue_keys", "jql", "project", "saved_filter", "page_ids", "cql", "space"]
    target_spec: dict
    comment_mode: Literal["personalized", "shared_context", "fixed"] = "personalized"
    instruction: str = Field(default="Provide a factual follow-up.", max_length=10000)
    fixed_comment: str = Field(default="", max_length=30000)
    language: Literal["fa", "en"] = "fa"
    tone: Literal["formal", "technical", "concise", "executive", "follow_up", "incident_response"] = "formal"
    mode: Literal["require_approval", "auto_post"] = "require_approval"
    skip_statuses: list[str] = Field(default_factory=list)
    approved: bool = False
    idempotency_key: str = Field(min_length=8, max_length=120)
    correlation_id: str = ""

    @field_validator("fixed_comment")
    @classmethod
    def fixed_comment_required(cls, value: str, info):
        if info.data.get("comment_mode") == "fixed" and not value.strip():
            raise ValueError("fixed_comment is required in fixed mode")
        return value


def _error(error: AtlassianError) -> HTTPException:
    return HTTPException(status_code=error.status_code if 400 <= error.status_code < 500 else 502, detail=error.as_dict())


def _provider(db: Session, connection: AtlassianConnection, product: str):
    transport = AtlassianTransport(db, connection, product)
    provider = JiraProvider(transport, connection.deployment_type == "cloud") if product == "jira" else ConfluenceProvider(transport, connection.deployment_type == "cloud")
    return transport, provider


def _mapping_dict(row: AtlassianFieldMapping) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _history_dict(row: IntegrationHistory) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


@router.get("/connections")
def connections(db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    rows = db.query(AtlassianConnection).filter(AtlassianConnection.tenant_id == context.tenant_id).order_by(AtlassianConnection.name).all()
    return [safe_connection(row) for row in rows]


@router.post("/connections")
def create_connection(payload: ConnectionIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    try:
        row = create_or_update(db, context, payload.model_dump())
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    audit(db, context, "atlassian.connection.create", "connection", str(row.id), connection_id=row.id)
    return safe_connection(row)


@router.put("/connections/{connection_id}")
def update_connection(connection_id: int, payload: ConnectionIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    try:
        row = scoped_connection(db, context, connection_id)
        row = create_or_update(db, context, payload.model_dump(), row)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    audit(db, context, "atlassian.connection.update", "connection", str(row.id), connection_id=row.id)
    return safe_connection(row)


@router.delete("/connections/{connection_id}")
def delete_connection(connection_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    try:
        row = scoped_connection(db, context, connection_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    audit(db, context, "atlassian.connection.delete", "connection", str(row.id), connection_id=row.id)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/connections/{connection_id}/test")
def test_connection(connection_id: int, issue_key: str = "", page_id: str = "", db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    try:
        row = scoped_connection(db, context, connection_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    result: dict[str, Any] = {}
    row.last_test_at = datetime.now(timezone.utc)
    try:
        for product in row.products:
            transport, provider = _provider(db, row, product)
            try:
                result[product] = provider.capability_preflight(issue_key=issue_key) if product == "jira" else provider.capability_preflight(page_id=page_id)
            finally:
                transport.close()
        row.last_success_at = datetime.now(timezone.utc)
        row.last_error_code = ""
        row.last_error_summary = ""
    except (AtlassianError, ValueError) as error:
        if isinstance(error, AtlassianError):
            row.last_error_code = error.code
            row.last_error_summary = error.message
            detail = error.as_dict()
        else:
            row.last_error_code = "credential_error"
            row.last_error_summary = str(error)
            detail = {"code": "credential_error", "message": str(error)}
        db.add(row)
        db.commit()
        audit(db, context, "atlassian.connection.test", "connection", str(row.id), connection_id=row.id, status="failed", details=detail)
        raise HTTPException(400, detail) from error
    db.add(row)
    db.commit()
    audit(db, context, "atlassian.connection.test", "connection", str(row.id), connection_id=row.id, details={"products": row.products})
    return {"ok": True, "capabilities": result, "tested_at": row.last_test_at}


@router.get("/connections/{connection_id}/oauth/start")
def oauth_start(connection_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    try:
        row = scoped_connection(db, context, connection_id)
        return {"authorization_url": oauth_authorization_url(row, context)}
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.get("/oauth/callback", include_in_schema=False)
def oauth_complete(code: str, state: str, db: Session = Depends(get_db)):
    try:
        oauth_callback(db, code, state)
    except (ValueError, httpx.HTTPError) as error:
        return RedirectResponse(url="/atlassian?oauth=failed")
    return RedirectResponse(url="/atlassian?oauth=success")


@router.get("/connections/{connection_id}/jira/projects")
def jira_projects(connection_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    row = scoped_connection(db, context, connection_id)
    transport, provider = _provider(db, row, "jira")
    try:
        return provider.list_projects(100)
    except AtlassianError as error:
        raise _error(error) from error
    finally:
        transport.close()


@router.get("/connections/{connection_id}/jira/issue-types")
def jira_issue_types(connection_id: int, project_key: str, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    row = scoped_connection(db, context, connection_id)
    transport, provider = _provider(db, row, "jira")
    try:
        return provider.issue_types(project_key)
    except AtlassianError as error:
        raise _error(error) from error
    finally:
        transport.close()


@router.get("/connections/{connection_id}/jira/fields")
def jira_fields(connection_id: int, project_key: str = "", issue_type_id: str = "", db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    row = scoped_connection(db, context, connection_id)
    transport, provider = _provider(db, row, "jira")
    try:
        fields = provider.list_fields(project_key, issue_type_id)
    except AtlassianError as error:
        raise _error(error) from error
    finally:
        transport.close()
    version = metadata_version(fields)
    known = {field["id"]: field for field in fields}
    mappings = db.query(AtlassianFieldMapping).filter(
        AtlassianFieldMapping.tenant_id == context.tenant_id,
        AtlassianFieldMapping.connection_id == connection_id,
        AtlassianFieldMapping.product == "jira",
    ).all()
    for mapping in mappings:
        field = known.get(mapping.external_field_id)
        errors = ["Field no longer exists in Jira"] if field is None else validate_definition(_mapping_dict(mapping), field)
        mapping.status = "stale" if field is None else "invalid" if errors else "valid"
        mapping.validation_message = "; ".join(errors)
        mapping.metadata_version = version
        mapping.last_validated_at = datetime.now(timezone.utc)
    db.commit()
    return {"metadata_version": version, "fields": fields}


@router.get("/internal-fields")
def internal_fields(_: AuthContext = Depends(get_auth_context)):
    return INTERNAL_FIELDS


@router.get("/connections/{connection_id}/confluence/metadata-fields")
def confluence_metadata_fields(connection_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    connection = scoped_connection(db, context, connection_id)
    if "confluence" not in (connection.products or []):
        raise HTTPException(422, "Confluence is not enabled on this connection")
    # These are provider capabilities rather than site-specific IDs. Spaces and
    # pages themselves remain dynamic through the Confluence APIs.
    return {"fields": [
        {"id": "space", "name": "Space", "type": "string", "schema": {"source": "spaceId/space.key"}, "required": True, "read_only": False},
        {"id": "title", "name": "Page title", "type": "string", "schema": {}, "required": True, "read_only": False},
        {"id": "labels", "name": "Labels", "type": "labels", "schema": {}, "required": False, "read_only": False},
        {"id": "owner", "name": "Owner / author", "type": "user", "schema": {}, "required": False, "read_only": False},
        {"id": "parent", "name": "Parent page", "type": "string", "schema": {}, "required": False, "read_only": False},
        {"id": "content_type", "name": "Content type", "type": "select", "schema": {"allowed": ["page", "blogpost"]}, "required": True, "read_only": False},
        {"id": "custom_metadata", "name": "Custom content property", "type": "string", "schema": {"key_required": True}, "required": False, "read_only": False},
        {"id": "version", "name": "Version", "type": "number", "schema": {}, "required": False, "read_only": True},
    ]}


@router.get("/connections/{connection_id}/mappings")
def mappings(connection_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    scoped_connection(db, context, connection_id)
    rows = db.query(AtlassianFieldMapping).filter(
        AtlassianFieldMapping.tenant_id == context.tenant_id,
        AtlassianFieldMapping.connection_id == connection_id,
    ).order_by(AtlassianFieldMapping.scope_type, AtlassianFieldMapping.internal_field).all()
    return [_mapping_dict(row) for row in rows]


@router.post("/connections/{connection_id}/mappings")
def create_mapping(connection_id: int, payload: MappingIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    scoped_connection(db, context, connection_id)
    errors = validate_definition(payload.model_dump())
    if errors:
        raise HTTPException(422, {"code": "invalid_mapping", "errors": errors})
    row = AtlassianFieldMapping(
        tenant_id=context.tenant_id,
        owner_user_id=context.username,
        connection_id=connection_id,
        **payload.model_dump(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, context, "atlassian.mapping.create", "field_mapping", str(row.id), connection_id=connection_id)
    return _mapping_dict(row)


@router.put("/mappings/{mapping_id}")
def update_mapping(mapping_id: int, payload: MappingIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    row = db.query(AtlassianFieldMapping).filter(
        AtlassianFieldMapping.id == mapping_id,
        AtlassianFieldMapping.tenant_id == context.tenant_id,
    ).first()
    if row is None:
        raise HTTPException(404, "Mapping not found")
    errors = validate_definition(payload.model_dump())
    if errors:
        raise HTTPException(422, {"code": "invalid_mapping", "errors": errors})
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.status = "valid"
    row.validation_message = ""
    db.commit()
    audit(db, context, "atlassian.mapping.update", "field_mapping", str(row.id), connection_id=row.connection_id)
    return _mapping_dict(row)


@router.delete("/mappings/{mapping_id}")
def delete_mapping(mapping_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    row = db.query(AtlassianFieldMapping).filter(AtlassianFieldMapping.id == mapping_id, AtlassianFieldMapping.tenant_id == context.tenant_id).first()
    if row is None:
        raise HTTPException(404, "Mapping not found")
    connection_id = row.connection_id
    db.delete(row)
    db.commit()
    audit(db, context, "atlassian.mapping.delete", "field_mapping", str(mapping_id), connection_id=connection_id)
    return {"ok": True}


@router.post("/connections/{connection_id}/mappings/preview")
def mapping_preview(connection_id: int, payload: MappingPreviewIn, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    connection = scoped_connection(db, context, connection_id)
    rows = resolve_mappings(db, context.tenant_id, connection_id, payload.project_key, payload.issue_type_id)
    return preview_mapping(rows, payload.source, cloud=connection.deployment_type == "cloud")


@router.get("/connections/{connection_id}/mappings/export")
def export_mappings(connection_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    scoped_connection(db, context, connection_id)
    rows = db.query(AtlassianFieldMapping).filter(AtlassianFieldMapping.tenant_id == context.tenant_id, AtlassianFieldMapping.connection_id == connection_id).all()
    payload = [{key: value for key, value in _mapping_dict(row).items() if key not in {"id", "tenant_id", "owner_user_id", "connection_id", "created_at", "updated_at"}} for row in rows]
    return {"version": 1, "connection_id": connection_id, "mappings": payload}


@router.post("/connections/{connection_id}/mappings/import")
def import_mappings(connection_id: int, payload: dict, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    scoped_connection(db, context, connection_id)
    created = 0
    errors: list[dict] = []
    for index, item in enumerate(payload.get("mappings") or []):
        try:
            parsed = MappingIn.model_validate(item)
            definition_errors = validate_definition(parsed.model_dump())
            if definition_errors:
                raise ValueError("; ".join(definition_errors))
            # A savepoint keeps one invalid/duplicate row from rolling back the
            # mappings that were already imported successfully.
            with db.begin_nested():
                db.add(AtlassianFieldMapping(tenant_id=context.tenant_id, owner_user_id=context.username, connection_id=connection_id, **parsed.model_dump()))
                db.flush()
            created += 1
        except Exception as error:  # noqa: BLE001 - aggregate per-row import errors
            errors.append({"index": index, "error": str(error)[:300]})
    db.commit()
    audit(db, context, "atlassian.mapping.import", "connection", str(connection_id), connection_id=connection_id, status="partial" if errors else "success", details={"created": created, "errors": len(errors)})
    return {"created": created, "errors": errors}


@router.post("/connections/{connection_id}/jira/search")
def jira_search(connection_id: int, payload: JiraSearchIn, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    row = scoped_connection(db, context, connection_id)
    started = time.perf_counter()
    trace = correlation_id()
    transport, provider = _provider(db, row, "jira")
    try:
        result = provider.search(payload.jql, payload.max_results)
        issues = result.get("issues", [])
        status, error_code, error_summary = "success", "", ""
    except AtlassianError as error:
        issues = []
        status, error_code, error_summary = "failed", error.code, error.message
        record_history(db, context, connection_id=connection_id, product="jira", operation_type="search", query_type="jql", query=payload.jql, final_query=payload.jql, status=status, duration_ms=int((time.perf_counter() - started) * 1000), error_code=error_code, error_summary=error_summary, trace_id=trace)
        raise _error(error) from error
    finally:
        transport.close()
    record_history(db, context, connection_id=connection_id, product="jira", operation_type="search", query_type="jql", query=payload.jql, final_query=payload.jql, target_keys=[item.get("key", "") for item in issues], result_summary=f"{len(issues)} issues returned", status=status, duration_ms=int((time.perf_counter() - started) * 1000), result_count=len(issues), trace_id=trace)
    return {"issues": issues, "total": result.get("total", len(issues)), "correlation_id": trace}


@router.get("/report-templates")
def jira_report_templates(context: AuthContext = Depends(get_auth_context)):
    """Return version-controlled default prompts used by the KPI workspace."""
    return REPORT_TEMPLATES


def _kpi_fields(payload: JiraKPIIn | JiraReportIn) -> list[str]:
    fields = [
        "summary", "status", "assignee", "priority", "project", "issuetype",
        "created", "updated", "resolutiondate", "duedate",
    ]
    for item in (payload.acknowledgement_field, payload.detection_field):
        if item and item not in fields:
            fields.append(item)
    return fields


def _calculate_connection_kpis(
    db: Session, context: AuthContext, connection: AtlassianConnection,
    payload: JiraKPIIn | JiraReportIn, jql: str,
) -> tuple[dict, dict, str, int]:
    trace = correlation_id()
    started = time.perf_counter()
    transport, provider = _provider(db, connection, "jira")
    try:
        search_result = provider.search(jql, payload.max_results, fields=_kpi_fields(payload))
    except AtlassianError as error:
        record_history(
            db, context, connection_id=connection.id, product="jira", operation_type="kpi",
            query_type="jql", query=jql, final_query=jql, status="failed",
            duration_ms=int((time.perf_counter() - started) * 1000), error_code=error.code,
            error_summary=error.message, trace_id=trace,
        )
        raise _error(error) from error
    finally:
        transport.close()
    issues = search_result.get("issues", [])
    result = calculate_soc_kpis(
        issues, sla_target_hours=payload.sla_target_hours,
        acknowledgement_field=payload.acknowledgement_field,
        detection_field=payload.detection_field,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    return result, search_result, trace, duration_ms


@router.post("/connections/{connection_id}/jira/kpis")
def jira_kpis(connection_id: int, payload: JiraKPIIn, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    connection = scoped_connection(db, context, connection_id)
    if "jira" not in (connection.products or []):
        raise HTTPException(422, {"code": "jira_not_enabled", "message": "Jira is not enabled for this connection."})
    result, search_result, trace, duration_ms = _calculate_connection_kpis(db, context, connection, payload, payload.jql)
    issue_count = len(search_result.get("issues", []))
    record_history(
        db, context, connection_id=connection_id, product="jira", operation_type="kpi",
        query_type="jql", query=payload.jql, final_query=payload.jql,
        result_summary=f"Calculated SOC KPIs from {issue_count} Jira issues", status="success",
        duration_ms=duration_ms, result_count=issue_count, trace_id=trace,
        metadata={"sla_target_hours": payload.sla_target_hours, "jira_total": search_result.get("total", issue_count)},
    )
    audit(db, context, "jira.kpi.calculate", "connection", str(connection_id), connection_id=connection_id, trace_id=trace, details={"issue_count": issue_count, "sla_target_hours": payload.sla_target_hours})
    return {**result, "jql": payload.jql, "jira_total": search_result.get("total", issue_count), "correlation_id": trace}


@router.post("/connections/{connection_id}/jira/reports")
def jira_report(connection_id: int, payload: JiraReportIn, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    connection = scoped_connection(db, context, connection_id)
    if "jira" not in (connection.products or []):
        raise HTTPException(422, {"code": "jira_not_enabled", "message": "Jira is not enabled for this connection."})
    try:
        template = report_template(payload.template_id)
        jql = render_template_jql(payload.template_id, payload.project_key)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error
    result, search_result, trace, duration_ms = _calculate_connection_kpis(db, context, connection, payload, jql)
    issue_count = len(search_result.get("issues", []))
    jira_total = search_result.get("total", issue_count)
    result["jira_total"] = jira_total
    markdown = render_markdown_report(template, payload.project_key, result)
    record_history(
        db, context, connection_id=connection_id, product="jira", operation_type="soc_report",
        query_type="report_template", prompt=template["prompt"], query=jql, final_query=jql,
        result_summary=markdown, status="success", duration_ms=duration_ms,
        result_count=issue_count, trace_id=trace,
        metadata={"template_id": payload.template_id, "project_key": payload.project_key.upper(), "sla_target_hours": payload.sla_target_hours, "jira_total": jira_total},
    )
    audit(db, context, "jira.report.generate", "connection", str(connection_id), connection_id=connection_id, trace_id=trace, details={"template_id": payload.template_id, "project_key": payload.project_key.upper(), "issue_count": issue_count})
    return {
        "template": template, "project_key": payload.project_key.upper(), "jql": jql,
        "report_markdown": markdown, "kpis": result,
        "jira_total": jira_total, "correlation_id": trace,
    }


@router.post("/connections/{connection_id}/jira/issues/{issue_key}/comments/preview")
def preview_jira_comment(connection_id: int, issue_key: str, payload: CommentPreviewIn, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    connection = scoped_connection(db, context, connection_id)
    if not connection.sorin_enabled:
        raise HTTPException(403, {"code": "sorin_disabled", "message": "Sorin processing is disabled for this connection."})
    transport, provider = _provider(db, connection, "jira")
    try:
        issue_context = provider.issue_context(issue_key)
        capabilities = provider.capability_preflight(issue_key=issue_key)
    except AtlassianError as error:
        raise _error(error) from error
    finally:
        transport.close()
    cfg = llm.config_from_settings(get_all_resolved(db))
    generated = generate_comment(issue_context, payload.instruction, payload.language, payload.tone, cfg)
    duplicate = is_similar_comment(generated.text, issue_context.get("comments") or [])
    trace = correlation_id()
    record_history(db, context, connection_id=connection_id, product="jira", operation_type="comment_preview", query_type="comment_generation", prompt=payload.instruction, target_keys=[issue_key], result_summary=generated.text, status="success", provider=generated.provider, model=generated.model, trace_id=trace, metadata={"language": payload.language, "tone": payload.tone, "duplicate_warning": duplicate})
    return {"comment": generated.text, "context": {key: value for key, value in issue_context.items() if key != "fields"}, "capabilities": capabilities, "duplicate_warning": duplicate, "conservative": generated.conservative, "provider": generated.provider, "model": generated.model, "correlation_id": trace}


@router.post("/connections/{connection_id}/jira/issues/{issue_key}/comments")
def post_jira_comment(connection_id: int, issue_key: str, payload: CommentPostIn, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    connection = scoped_connection(db, context, connection_id)
    if payload.mode == "suggest_only":
        raise HTTPException(409, {"code": "suggest_only", "message": "Suggest-only mode never posts comments."})
    if payload.mode == "require_approval" and not payload.approved:
        raise HTTPException(409, {"code": "approval_required", "message": "Explicit approval is required before posting."})
    if payload.mode == "auto_post" and (not connection.auto_post_enabled or context.role != "admin"):
        raise HTTPException(403, {"code": "auto_post_disabled", "message": "Auto-post requires an enabled connection policy and admin role."})
    request_hash = hashlib.sha256(f"{issue_key}\n{payload.text}".encode()).hexdigest()
    existing = db.query(IdempotencyRecord).filter(IdempotencyRecord.tenant_id == context.tenant_id, IdempotencyRecord.scope == f"jira-comment:{connection_id}", IdempotencyRecord.key == payload.idempotency_key).first()
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(409, {"code": "idempotency_conflict", "message": "Idempotency key was already used with different content."})
        return {**existing.response, "idempotent_replay": True}
    trace = correlation_id()
    started = time.perf_counter()
    transport, provider = _provider(db, connection, "jira")
    try:
        capabilities = provider.capability_preflight(issue_key=issue_key)
        if capabilities.get("can_add_comments", {}).get("allowed") is not True:
            raise AtlassianError("comment_permission_denied", "Jira reports that this user cannot add comments to the issue.", 403, False, "Grant Add Comments and Browse Projects permissions and verify issue security.")
        previous = [adf_to_text(item.get("body")) for item in provider.get_comments(issue_key, 50)]
        if is_similar_comment(payload.text, previous):
            raise AtlassianError("duplicate_comment", "A substantially similar comment already exists.", 409, False, "Edit the comment or explicitly generate a different update.")
        result = provider.add_comment(issue_key, payload.text, trace)
    except AtlassianError as error:
        record_history(db, context, connection_id=connection_id, product="jira", operation_type="comment_post", query_type="comment", prompt=payload.text, target_keys=[issue_key], status="failed", duration_ms=int((time.perf_counter() - started) * 1000), error_code=error.code, error_summary=error.message, trace_id=trace)
        audit(db, context, "jira.comment.post", "issue", issue_key, connection_id=connection_id, status="failed", trace_id=trace, details=error.as_dict())
        raise _error(error) from error
    finally:
        transport.close()
    response = {"ok": True, "comment_id": str(result.get("id", "")), "issue_key": issue_key, "correlation_id": trace}
    db.add(IdempotencyRecord(tenant_id=context.tenant_id, scope=f"jira-comment:{connection_id}", key=payload.idempotency_key, request_hash=request_hash, response=response))
    db.commit()
    record_history(db, context, connection_id=connection_id, product="jira", operation_type="comment_post", query_type="comment", prompt=payload.text, target_keys=[issue_key], result_summary=f"Comment {response['comment_id']} posted", status="success", duration_ms=int((time.perf_counter() - started) * 1000), result_count=1, trace_id=trace, metadata={"comment_id": response["comment_id"], "language": payload.language, "tone": payload.tone})
    audit(db, context, "jira.comment.post", "issue", issue_key, connection_id=connection_id, trace_id=trace, details={"comment_id": response["comment_id"]})
    return response


@router.get("/connections/{connection_id}/confluence/spaces")
def confluence_spaces(connection_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    row = scoped_connection(db, context, connection_id)
    transport, provider = _provider(db, row, "confluence")
    try:
        return provider.list_spaces(100)
    except AtlassianError as error:
        raise _error(error) from error
    finally:
        transport.close()


@router.post("/connections/{connection_id}/confluence/search")
def confluence_search(connection_id: int, payload: ConfluenceSearchIn, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    row = scoped_connection(db, context, connection_id)
    trace = correlation_id()
    started = time.perf_counter()
    transport, provider = _provider(db, row, "confluence")
    try:
        result = provider.search(payload.cql, payload.limit)
    except AtlassianError as error:
        record_history(db, context, connection_id=connection_id, product="confluence", operation_type="search", query_type="cql", query=payload.cql, final_query=payload.cql, status="failed", duration_ms=int((time.perf_counter() - started) * 1000), error_code=error.code, error_summary=error.message, trace_id=trace)
        raise _error(error) from error
    finally:
        transport.close()
    results = result.get("results", [])
    record_history(db, context, connection_id=connection_id, product="confluence", operation_type="search", query_type="cql", query=payload.cql, final_query=payload.cql, target_keys=[str((item.get("content") or item).get("id", "")) for item in results], result_summary=f"{len(results)} pages returned", status="success", duration_ms=int((time.perf_counter() - started) * 1000), result_count=len(results), trace_id=trace)
    return {"results": results, "total": result.get("size", len(results)), "correlation_id": trace}


@router.get("/connections/{connection_id}/content-links")
def content_links(connection_id: int, jira_issue_key: str = "", confluence_page_id: str = "", db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    scoped_connection(db, context, connection_id)
    query = db.query(AtlassianContentLink).filter(
        AtlassianContentLink.tenant_id == context.tenant_id,
        AtlassianContentLink.connection_id == connection_id,
    )
    if jira_issue_key:
        query = query.filter(AtlassianContentLink.jira_issue_key == jira_issue_key.upper())
    if confluence_page_id:
        query = query.filter(AtlassianContentLink.confluence_page_id == confluence_page_id)
    return [{column.name: getattr(row, column.name) for column in row.__table__.columns} for row in query.order_by(desc(AtlassianContentLink.created_at)).all()]


@router.post("/connections/{connection_id}/content-links")
def create_content_link(connection_id: int, payload: ContentLinkIn, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    connection = scoped_connection(db, context, connection_id)
    if not {"jira", "confluence"}.issubset(set(connection.products or [])):
        raise HTTPException(422, {"code": "products_required", "message": "This link requires a connection with Jira and Confluence enabled."})
    issue_key = payload.jira_issue_key.upper()
    existing = db.query(AtlassianContentLink).filter(
        AtlassianContentLink.tenant_id == context.tenant_id,
        AtlassianContentLink.connection_id == connection_id,
        AtlassianContentLink.jira_issue_key == issue_key,
        AtlassianContentLink.confluence_page_id == payload.confluence_page_id,
    ).first()
    if existing:
        return {column.name: getattr(existing, column.name) for column in existing.__table__.columns}
    row = AtlassianContentLink(
        tenant_id=context.tenant_id, owner_user_id=context.username, connection_id=connection_id,
        jira_issue_key=issue_key, confluence_page_id=payload.confluence_page_id,
        relation_type=payload.relation_type,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    record_history(db, context, connection_id=connection_id, product="atlassian", operation_type="content_link", query_type="link", target_keys=[issue_key, payload.confluence_page_id], result_summary=f"Linked Jira {issue_key} to Confluence page {payload.confluence_page_id}", status="success")
    audit(db, context, "atlassian.content_link.create", "content_link", str(row.id), connection_id=connection_id, details={"jira_issue_key": issue_key, "confluence_page_id": payload.confluence_page_id})
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


@router.delete("/content-links/{link_id}")
def delete_content_link(link_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    row = db.query(AtlassianContentLink).filter(AtlassianContentLink.id == link_id, AtlassianContentLink.tenant_id == context.tenant_id).first()
    if row is None or (context.role != "admin" and row.owner_user_id != context.username):
        raise HTTPException(404, "Content link not found")
    connection_id = row.connection_id
    db.delete(row)
    db.commit()
    audit(db, context, "atlassian.content_link.delete", "content_link", str(link_id), connection_id=connection_id)
    return {"ok": True}


@router.get("/connections/{connection_id}/confluence/pages/{page_id}")
def confluence_page(connection_id: int, page_id: str, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    row = scoped_connection(db, context, connection_id)
    transport, provider = _provider(db, row, "confluence")
    try:
        return provider.page_context(page_id)
    except AtlassianError as error:
        raise _error(error) from error
    finally:
        transport.close()


@router.post("/connections/{connection_id}/confluence/pages/{page_id}/comments/preview")
def preview_confluence_comment(connection_id: int, page_id: str, payload: CommentPreviewIn, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    connection = scoped_connection(db, context, connection_id)
    if not connection.sorin_enabled:
        raise HTTPException(403, {"code": "sorin_disabled", "message": "Sorin processing is disabled for this connection."})
    transport, provider = _provider(db, connection, "confluence")
    try:
        page_context = provider.page_context(page_id)
        capabilities = provider.capability_preflight(page_id=page_id)
    except AtlassianError as error:
        raise _error(error) from error
    finally:
        transport.close()
    cfg = llm.config_from_settings(get_all_resolved(db))
    generated = generate_comment(page_context, payload.instruction, payload.language, payload.tone, cfg)
    duplicate = is_similar_comment(generated.text, page_context.get("comments") or [])
    trace = correlation_id()
    record_history(db, context, connection_id=connection_id, product="confluence", operation_type="comment_preview", query_type="comment_generation", prompt=payload.instruction, target_keys=[page_id], result_summary=generated.text, status="success", provider=generated.provider, model=generated.model, trace_id=trace, metadata={"language": payload.language, "tone": payload.tone, "duplicate_warning": duplicate})
    return {"comment": generated.text, "context": page_context, "capabilities": capabilities, "duplicate_warning": duplicate, "conservative": generated.conservative, "provider": generated.provider, "model": generated.model, "correlation_id": trace}


@router.post("/connections/{connection_id}/confluence/pages/{page_id}/comments")
def post_confluence_comment(connection_id: int, page_id: str, payload: CommentPostIn, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    connection = scoped_connection(db, context, connection_id)
    if payload.mode == "suggest_only":
        raise HTTPException(409, {"code": "suggest_only", "message": "Suggest-only mode never posts comments."})
    if payload.mode == "require_approval" and not payload.approved:
        raise HTTPException(409, {"code": "approval_required", "message": "Explicit approval is required before posting."})
    if payload.mode == "auto_post" and (not connection.auto_post_enabled or context.role != "admin"):
        raise HTTPException(403, {"code": "auto_post_disabled", "message": "Auto-post requires an enabled connection policy and admin role."})
    request_hash = hashlib.sha256(f"{page_id}\n{payload.text}".encode()).hexdigest()
    existing = db.query(IdempotencyRecord).filter(IdempotencyRecord.tenant_id == context.tenant_id, IdempotencyRecord.scope == f"confluence-comment:{connection_id}", IdempotencyRecord.key == payload.idempotency_key).first()
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(409, {"code": "idempotency_conflict", "message": "Idempotency key was already used with different content."})
        return {**existing.response, "idempotent_replay": True}
    trace = correlation_id()
    started = time.perf_counter()
    transport, provider = _provider(db, connection, "confluence")
    try:
        page_context = provider.page_context(page_id)
        if is_similar_comment(payload.text, page_context.get("comments") or []):
            raise AtlassianError("duplicate_comment", "A substantially similar comment already exists.", 409, False, "Edit the comment before posting.")
        result = provider.add_footer_comment(page_id, payload.text)
    except AtlassianError as error:
        record_history(db, context, connection_id=connection_id, product="confluence", operation_type="comment_post", query_type="comment", prompt=payload.text, target_keys=[page_id], status="failed", duration_ms=int((time.perf_counter() - started) * 1000), error_code=error.code, error_summary=error.message, trace_id=trace)
        audit(db, context, "confluence.comment.post", "page", page_id, connection_id=connection_id, status="failed", trace_id=trace, details=error.as_dict())
        raise _error(error) from error
    finally:
        transport.close()
    response = {"ok": True, "comment_id": str(result.get("id", "")), "page_id": page_id, "correlation_id": trace}
    db.add(IdempotencyRecord(tenant_id=context.tenant_id, scope=f"confluence-comment:{connection_id}", key=payload.idempotency_key, request_hash=request_hash, response=response))
    db.commit()
    record_history(db, context, connection_id=connection_id, product="confluence", operation_type="comment_post", query_type="comment", prompt=payload.text, target_keys=[page_id], result_summary=f"Comment {response['comment_id']} posted", status="success", duration_ms=int((time.perf_counter() - started) * 1000), result_count=1, trace_id=trace, metadata={"comment_id": response["comment_id"]})
    audit(db, context, "confluence.comment.post", "page", page_id, connection_id=connection_id, trace_id=trace, details={"comment_id": response["comment_id"]})
    return response


def _bulk_dict(row: BulkOperation, db: Session, include_items: bool = False) -> dict:
    data = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    if include_items:
        items = db.query(BulkOperationItem).filter(BulkOperationItem.bulk_operation_id == row.id).order_by(BulkOperationItem.id).all()
        data["items"] = [{column.name: getattr(item, column.name) for column in item.__table__.columns} for item in items]
    return data


@router.post("/connections/{connection_id}/bulk/preview")
def bulk_preview(connection_id: int, payload: BulkIn, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    connection = scoped_connection(db, context, connection_id)
    if payload.product not in connection.products:
        raise HTTPException(422, f"Connection does not enable {payload.product}")
    try:
        return bulk_operations.preview_bulk(db, connection, payload.model_dump())
    except (ValueError, AtlassianError) as error:
        if isinstance(error, AtlassianError):
            raise _error(error) from error
        raise HTTPException(422, str(error)) from error


@router.post("/connections/{connection_id}/bulk")
def create_bulk_operation(connection_id: int, payload: BulkIn, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    connection = scoped_connection(db, context, connection_id)
    if not payload.approved:
        raise HTTPException(409, {"code": "bulk_approval_required", "message": "Preview and explicit final approval are required."})
    if payload.mode == "auto_post" and (context.role != "admin" or not connection.bulk_auto_post_enabled):
        raise HTTPException(403, {"code": "bulk_auto_post_disabled", "message": "Bulk auto-post requires admin role and an enabled connection policy."})
    body = payload.model_dump()
    body["correlation_id"] = payload.correlation_id or correlation_id()
    try:
        row = bulk_operations.create_bulk(db, context, connection, body)
    except (ValueError, AtlassianError) as error:
        if isinstance(error, AtlassianError):
            raise _error(error) from error
        raise HTTPException(422, str(error)) from error
    if row.status == "pending":
        job_id = bulk_operations.start_bulk_job(row.id)
    else:
        job_id = None
    audit(db, context, "atlassian.bulk.create", "bulk_operation", str(row.id), connection_id=connection_id, trace_id=row.correlation_id, details={"total": row.total_count, "job_id": job_id})
    return {**_bulk_dict(row, db), "job_id": job_id}


@router.get("/bulk")
def list_bulk_operations(status: str = "", page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100), db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    query = db.query(BulkOperation).filter(BulkOperation.tenant_id == context.tenant_id)
    if context.role != "admin":
        query = query.filter(BulkOperation.owner_user_id == context.username)
    if status:
        query = query.filter(BulkOperation.status == status)
    total = query.count()
    rows = query.order_by(desc(BulkOperation.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [_bulk_dict(row, db) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/bulk/{bulk_id}")
def get_bulk_operation(bulk_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    row = db.query(BulkOperation).filter(BulkOperation.id == bulk_id, BulkOperation.tenant_id == context.tenant_id).first()
    if row is None or (context.role != "admin" and row.owner_user_id != context.username):
        raise HTTPException(404, "Bulk operation not found")
    return _bulk_dict(row, db, include_items=True)


@router.post("/bulk/{bulk_id}/cancel")
def cancel_bulk_operation(bulk_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    row = db.query(BulkOperation).filter(BulkOperation.id == bulk_id, BulkOperation.tenant_id == context.tenant_id).first()
    if row is None or (context.role != "admin" and row.owner_user_id != context.username):
        raise HTTPException(404, "Bulk operation not found")
    if row.status not in {"pending", "running", "paused"}:
        raise HTTPException(409, "Only active bulk operations can be cancelled")
    row.cancellation_requested = True
    db.commit()
    audit(db, context, "atlassian.bulk.cancel", "bulk_operation", str(row.id), connection_id=row.connection_id, trace_id=row.correlation_id)
    return {"ok": True}


@router.post("/bulk/{bulk_id}/pause")
def pause_bulk_operation(bulk_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    row = db.query(BulkOperation).filter(BulkOperation.id == bulk_id, BulkOperation.tenant_id == context.tenant_id).first()
    if row is None:
        raise HTTPException(404, "Bulk operation not found")
    row.paused = True
    row.status = "paused"
    db.commit()
    audit(db, context, "atlassian.bulk.pause", "bulk_operation", str(row.id), connection_id=row.connection_id, trace_id=row.correlation_id)
    return {"ok": True}


@router.post("/bulk/{bulk_id}/resume")
def resume_bulk_operation(bulk_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    row = db.query(BulkOperation).filter(BulkOperation.id == bulk_id, BulkOperation.tenant_id == context.tenant_id).first()
    if row is None:
        raise HTTPException(404, "Bulk operation not found")
    was_terminal = row.status in {"failed", "partial", "cancelled"}
    row.paused = False
    row.cancellation_requested = False
    row.status = "pending" if was_terminal else "running"
    if was_terminal:
        for item in db.query(BulkOperationItem).filter(BulkOperationItem.bulk_operation_id == bulk_id, BulkOperationItem.status == "failed"):
            item.status = "pending"
    db.commit()
    job_id = bulk_operations.start_bulk_job(row.id) if was_terminal else None
    audit(db, context, "atlassian.bulk.resume", "bulk_operation", str(row.id), connection_id=row.connection_id, trace_id=row.correlation_id)
    return {"ok": True, "job_id": job_id}


@router.get("/history")
def history(
    connection_id: int | None = None,
    owner_user_id: str = "",
    product: str = "",
    operation_type: str = "",
    status: str = "",
    project_key: str = "",
    issue: str = "",
    started_after: datetime | None = None,
    started_before: datetime | None = None,
    search: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    query = db.query(IntegrationHistory).filter(
        IntegrationHistory.tenant_id == context.tenant_id,
        IntegrationHistory.deleted_at.is_(None),
    )
    if context.role != "admin":
        query = query.filter(IntegrationHistory.owner_user_id == context.username)
    elif owner_user_id:
        query = query.filter(IntegrationHistory.owner_user_id == owner_user_id[:120])
    if connection_id is not None:
        query = query.filter(IntegrationHistory.connection_id == connection_id)
    if product:
        query = query.filter(IntegrationHistory.product == product)
    if operation_type:
        query = query.filter(IntegrationHistory.operation_type == operation_type)
    if status:
        query = query.filter(IntegrationHistory.status == status)
    if project_key:
        query = query.filter(IntegrationHistory.project_key == project_key)
    if issue:
        query = query.filter(IntegrationHistory.target_keys.contains(issue))
    if started_after:
        query = query.filter(IntegrationHistory.created_at >= started_after)
    if started_before:
        query = query.filter(IntegrationHistory.created_at <= started_before)
    if search:
        pattern = f"%{search[:200]}%"
        query = query.filter(or_(IntegrationHistory.query_redacted.ilike(pattern), IntegrationHistory.prompt_redacted.ilike(pattern), IntegrationHistory.result_summary.ilike(pattern)))
    total = query.count()
    rows = query.order_by(desc(IntegrationHistory.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [_history_dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/history/{history_id}")
def history_detail(history_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    row = db.query(IntegrationHistory).filter(IntegrationHistory.id == history_id, IntegrationHistory.tenant_id == context.tenant_id, IntegrationHistory.deleted_at.is_(None)).first()
    if row is None or (context.role != "admin" and row.owner_user_id != context.username):
        raise HTTPException(404, "History item not found")
    return _history_dict(row)


@router.delete("/history/{history_id}")
def delete_history(history_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    row = db.query(IntegrationHistory).filter(IntegrationHistory.id == history_id, IntegrationHistory.tenant_id == context.tenant_id).first()
    if row is None or (context.role != "admin" and row.owner_user_id != context.username):
        raise HTTPException(404, "History item not found")
    row.deleted_at = datetime.now(timezone.utc)
    db.commit()
    audit(db, context, "atlassian.history.delete", "history", str(history_id), connection_id=row.connection_id)
    return {"ok": True}


@router.get("/history-exports/{format}")
def export_history(format: Literal["json", "csv"], db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    rows = db.query(IntegrationHistory).filter(IntegrationHistory.tenant_id == context.tenant_id, IntegrationHistory.deleted_at.is_(None)).order_by(desc(IntegrationHistory.created_at)).limit(10000).all()
    data = [_history_dict(row) for row in rows]
    if format == "json":
        body = json.dumps(data, ensure_ascii=False, default=str, indent=2)
        return StreamingResponse(io.BytesIO(body.encode()), media_type="application/json", headers={"Content-Disposition": "attachment; filename=atlassian-history.json"})
    output = io.StringIO()
    columns = ["id", "product", "operation_type", "query_type", "query_redacted", "target_keys", "status", "duration_ms", "error_code", "result_count", "provider", "model", "correlation_id", "created_at"]
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for item in data:
        writer.writerow({key: json.dumps(item.get(key), ensure_ascii=False, default=str) if isinstance(item.get(key), (list, dict)) else item.get(key) for key in columns})
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=atlassian-history.csv"})
