"""Tenant-scoped integration history, redaction and audit helpers."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..models.atlassian import AuditLog, IntegrationHistory
from ..security import AuthContext
from .atlassian_http import redact_error
from .sensitive_data import protect

INLINE_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|token|password|secret|authorization|cookie)\b\s*[:=]\s*([^\s,;]+)"
)


def correlation_id() -> str:
    return uuid.uuid4().hex


def redact_text(db: Session, value: str) -> str:
    if not value:
        return ""
    first = INLINE_SECRET.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    return protect(first, mode="mask", db=db).text[:50000]


def _safe_details(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if any(part in key.lower() for part in ("token", "password", "secret", "cookie", "authorization")) else _safe_details(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_safe_details(item) for item in value]
    if isinstance(value, str):
        return redact_error(value)
    return value


def record_history(
    db: Session,
    context: AuthContext,
    *,
    connection_id: int | None,
    product: str,
    operation_type: str,
    query_type: str = "",
    prompt: str = "",
    query: str = "",
    final_query: str = "",
    target_keys: list[str] | None = None,
    project_key: str = "",
    result_summary: str = "",
    status: str = "success",
    duration_ms: int = 0,
    error_code: str = "",
    error_summary: str = "",
    result_count: int = 0,
    provider: str = "",
    model: str = "",
    trace_id: str = "",
    metadata: dict | None = None,
) -> IntegrationHistory:
    row = IntegrationHistory(
        tenant_id=context.tenant_id,
        owner_user_id=context.username,
        connection_id=connection_id,
        product=product,
        operation_type=operation_type,
        query_type=query_type,
        prompt_redacted=redact_text(db, prompt),
        query_redacted=redact_text(db, query),
        final_query=redact_text(db, final_query),
        target_keys=target_keys or [],
        project_key=project_key,
        result_summary=redact_text(db, result_summary),
        status=status,
        duration_ms=duration_ms,
        error_code=error_code,
        error_summary=redact_text(db, error_summary),
        result_count=result_count,
        provider=provider,
        model=model,
        correlation_id=trace_id or correlation_id(),
        history_metadata=_safe_details(metadata or {}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def audit(
    db: Session, context: AuthContext, action: str, resource_type: str, resource_id: str,
    *, connection_id: int | None = None, status: str = "success", trace_id: str = "", details: dict | None = None,
) -> AuditLog:
    row = AuditLog(
        tenant_id=context.tenant_id,
        actor_user_id=context.username,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        connection_id=connection_id,
        status=status,
        correlation_id=trace_id or correlation_id(),
        details=_safe_details(details or {}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def enforce_retention(db: Session, tenant_id: str, days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(days, 1))
    rows = db.query(IntegrationHistory).filter(
        IntegrationHistory.tenant_id == tenant_id,
        IntegrationHistory.created_at < cutoff,
    ).delete(synchronize_session=False)
    db.commit()
    return rows

