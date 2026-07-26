"""Declarative, non-executable Atlassian field mapping and validation."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models.atlassian import AtlassianFieldMapping
from .jira_provider import adf_document

INTERNAL_FIELDS = [
    {"id": "title", "name": "Title / Summary", "type": "string"},
    {"id": "description", "name": "Description", "type": "rich_text"},
    {"id": "status", "name": "Status", "type": "status"},
    {"id": "priority", "name": "Priority", "type": "priority"},
    {"id": "assignee", "name": "Assignee", "type": "user"},
    {"id": "reporter", "name": "Reporter", "type": "user"},
    {"id": "labels", "name": "Labels", "type": "labels"},
    {"id": "components", "name": "Components", "type": "components"},
    {"id": "customer", "name": "Customer", "type": "string"},
    {"id": "severity", "name": "Severity", "type": "select"},
    {"id": "confidence", "name": "Confidence", "type": "number"},
    {"id": "due_date", "name": "Due date", "type": "date"},
    {"id": "created_at", "name": "Created at", "type": "datetime"},
    {"id": "ioc_values", "name": "IoC values", "type": "multi_select"},
    {"id": "analysis", "name": "Analysis result", "type": "rich_text"},
]

COMPATIBLE: dict[str, set[str]] = {
    "string": {"string", "select", "description", "rich_text"},
    "number": {"number", "string"},
    "date": {"date", "datetime", "string"},
    "datetime": {"datetime", "date", "string"},
    "select": {"select", "string", "priority", "status"},
    "multi_select": {"multi_select", "labels", "components", "string"},
    "user": {"user", "string"},
    "group": {"group", "string"},
    "labels": {"labels", "multi_select", "string"},
    "components": {"components", "multi_select", "string"},
    "priority": {"priority", "select", "string"},
    "status": {"status", "select", "string"},
    "description": {"description", "rich_text", "string"},
    "rich_text": {"rich_text", "description", "string"},
}

ALLOWED_TRANSFORMS = {
    "identity", "stringify", "number", "date_format", "join", "split",
    "map_values", "option", "user", "components", "adf",
}


def metadata_version(fields: list[dict]) -> str:
    canonical = [{"id": item.get("id"), "name": item.get("name"), "type": item.get("type")} for item in fields]
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()[:24]


def validate_definition(mapping: dict, field: dict | None = None) -> list[str]:
    errors: list[str] = []
    if mapping.get("scope_type") not in {"connection", "project", "issue_type"}:
        errors.append("scope_type must be connection, project, or issue_type")
    if mapping.get("scope_type") in {"project", "issue_type"} and not mapping.get("project_key"):
        errors.append("project_key is required for project and issue_type mappings")
    if mapping.get("scope_type") == "issue_type" and not mapping.get("issue_type_id"):
        errors.append("issue_type_id is required for issue_type mappings")
    if mapping.get("read_only"):
        errors.append("Target field is read-only")
    transform = mapping.get("transformation") or {"op": "identity"}
    if transform.get("op", "identity") not in ALLOWED_TRANSFORMS:
        errors.append("Unsupported transformation; executable expressions are not allowed")
    if field:
        if field.get("read_only") and not mapping.get("read_only"):
            errors.append("Target Jira field is read-only")
        internal = mapping.get("internal_type", "string")
        external = field.get("type", mapping.get("external_type", "string"))
        if external not in COMPATIBLE.get(internal, {internal}) and transform.get("op", "identity") == "identity":
            errors.append(f"{internal} is not directly compatible with {external}; select a transformation")
    return errors


def transform_value(value: Any, transformation: dict, *, cloud: bool = True) -> Any:
    op = (transformation or {}).get("op", "identity")
    if value is None:
        return None
    if op == "identity":
        return value
    if op == "stringify":
        return str(value)
    if op == "number":
        return float(value) if "." in str(value) else int(value)
    if op == "date_format":
        if isinstance(value, (datetime, date)):
            return value.strftime(transformation.get("format", "%Y-%m-%d"))
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime(transformation.get("format", "%Y-%m-%d"))
    if op == "join":
        return transformation.get("separator", ", ").join(str(item) for item in (value if isinstance(value, list) else [value]))
    if op == "split":
        return [item.strip() for item in str(value).split(transformation.get("separator", ",")) if item.strip()]
    if op == "map_values":
        mapping = transformation.get("values") or {}
        if isinstance(value, list):
            return [mapping.get(str(item), item) for item in value]
        return mapping.get(str(value), value)
    if op == "option":
        return {"value": str(value)}
    if op == "user":
        key = "accountId" if cloud else "name"
        return {key: str(value)}
    if op == "components":
        values = value if isinstance(value, list) else [value]
        return [{"name": str(item)} for item in values]
    if op == "adf":
        return adf_document(str(value)) if cloud else str(value)
    raise ValueError(f"Unsupported transformation: {op}")


def resolve_mappings(
    db: Session, tenant_id: str, connection_id: int, project_key: str = "", issue_type_id: str = "",
) -> list[AtlassianFieldMapping]:
    rows = db.query(AtlassianFieldMapping).filter(
        AtlassianFieldMapping.tenant_id == tenant_id,
        AtlassianFieldMapping.connection_id == connection_id,
        AtlassianFieldMapping.status != "invalid",
        or_(
            AtlassianFieldMapping.scope_type == "connection",
            (AtlassianFieldMapping.scope_type == "project") & (AtlassianFieldMapping.project_key == project_key),
            (AtlassianFieldMapping.scope_type == "issue_type")
            & (AtlassianFieldMapping.project_key == project_key)
            & (AtlassianFieldMapping.issue_type_id == issue_type_id),
        ),
    ).all()
    rank = {"connection": 0, "project": 1, "issue_type": 2}
    selected: dict[str, AtlassianFieldMapping] = {}
    for row in sorted(rows, key=lambda item: rank.get(item.scope_type, 0)):
        selected[row.internal_field] = row
    return list(selected.values())


def preview_mapping(rows: list[AtlassianFieldMapping], source: dict, *, cloud: bool) -> dict:
    output: dict[str, Any] = {}
    warnings: list[str] = []
    for row in rows:
        value = source.get(row.internal_field)
        if row.required and value in (None, "", []):
            warnings.append(f"{row.external_field_name or row.external_field_id} is required but has no value")
            continue
        if value is None:
            continue
        try:
            output[row.external_field_id] = transform_value(value, row.transformation, cloud=cloud)
        except (ValueError, TypeError) as error:
            warnings.append(f"{row.internal_field}: {error}")
    return {"fields": output, "warnings": warnings, "valid": not warnings}
