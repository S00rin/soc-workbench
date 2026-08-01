"""Persisted, bounded Atlassian bulk comment orchestration."""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal
from ..models.atlassian import AtlassianConnection, BulkOperation, BulkOperationItem
from ..security import AuthContext
from . import jobs, llm
from .sorin_comments import generate_comment, is_similar_comment
from .atlassian_http import AtlassianError, AtlassianTransport
from .confluence_provider import ConfluenceProvider
from .integration_history import audit, record_history, redact_text
from .jira_provider import JiraProvider, adf_to_text
from .settings_service import get_all_resolved, get_value


def _providers(db: Session, connection: AtlassianConnection, product: str):
    transport = AtlassianTransport(db, connection, product)
    provider = JiraProvider(transport, connection.deployment_type == "cloud") if product == "jira" else ConfluenceProvider(transport, connection.deployment_type == "cloud")
    return transport, provider


def resolve_targets(db: Session, connection: AtlassianConnection, product: str, target_type: str, target_spec: dict) -> list[str]:
    transport, provider = _providers(db, connection, product)
    try:
        if product == "jira":
            if target_type == "issue_keys":
                keys = target_spec.get("issue_keys") or []
            else:
                if target_type == "project":
                    project_key = str(target_spec.get("project_key", "")).strip()
                    if not project_key:
                        raise ValueError("project_key is required")
                    project_key = project_key.replace('"', "")
                    query = f'project = "{project_key}" ORDER BY key'
                elif target_type == "saved_filter":
                    filter_id = str(target_spec.get("filter_id", "")).strip()
                    if not filter_id.isdigit():
                        raise ValueError("A numeric filter_id is required")
                    query = f"filter = {filter_id} ORDER BY key"
                else:
                    query = str(target_spec.get("jql", "")).strip()
                if not query:
                    raise ValueError("A bounded JQL query is required")
                keys = [item.get("key", "") for item in provider.search(query, get_settings().atlassian_bulk_max_issues + 1).get("issues", [])]
        else:
            if target_type == "page_ids":
                keys = target_spec.get("page_ids") or []
            else:
                cql = str(target_spec.get("cql", "")).strip()
                if target_type == "space":
                    space = str(target_spec.get("space_key", "")).replace('"', "")
                    cql = f'space = "{space}" and type = page'
                if not cql:
                    raise ValueError("A bounded CQL query is required")
                results = provider.search(cql, min(get_settings().atlassian_bulk_max_issues + 1, 100)).get("results", [])
                keys = [str((item.get("content") or item).get("id", "")) for item in results]
    finally:
        transport.close()
    return list(dict.fromkeys(str(key).strip() for key in keys if str(key).strip()))


def preview_bulk(
    db: Session, connection: AtlassianConnection, payload: dict,
) -> dict:
    product = payload.get("product", "jira")
    targets = resolve_targets(db, connection, product, payload.get("target_type", "issue_keys"), payload.get("target_spec") or {})
    configured_limit = int(get_value(db, "atlassian_bulk_max_issues", str(get_settings().atlassian_bulk_max_issues)) or get_settings().atlassian_bulk_max_issues)
    if len(targets) > configured_limit:
        raise ValueError(f"Target count {len(targets)} exceeds the admin limit of {configured_limit}")
    sample: list[dict] = []
    transport, provider = _providers(db, connection, product)
    try:
        cfg = llm.config_from_settings(get_all_resolved(db))
        for target in targets[:3]:
            context = provider.issue_context(target) if product == "jira" else provider.page_context(target)
            if payload.get("comment_mode") == "fixed":
                comment = payload.get("fixed_comment", "")
            else:
                generated = generate_comment(
                    context,
                    payload.get("instruction", "Provide a factual follow-up."),
                    payload.get("language", "fa"),
                    payload.get("tone", "formal"),
                    cfg,
                )
                comment = generated.text
            sample.append({"target": target, "title": context.get("summary") or context.get("title"), "status": context.get("status", ""), "comment": comment})
    finally:
        transport.close()
    return {"target_count": len(targets), "targets": targets, "sample": sample, "limit": configured_limit}


def create_bulk(
    db: Session, context: AuthContext, connection: AtlassianConnection, payload: dict,
) -> BulkOperation:
    preview = preview_bulk(db, connection, payload)
    idempotency_key = payload["idempotency_key"]
    existing = db.query(BulkOperation).filter(
        BulkOperation.tenant_id == context.tenant_id,
        BulkOperation.idempotency_key == idempotency_key,
    ).first()
    if existing:
        return existing
    row = BulkOperation(
        tenant_id=context.tenant_id,
        owner_user_id=context.username,
        connection_id=connection.id,
        product=payload.get("product", "jira"),
        target_type=payload.get("target_type", "issue_keys"),
        target_spec=payload.get("target_spec") or {},
        comment_config={
            "comment_mode": payload.get("comment_mode", "personalized"),
            "instruction": payload.get("instruction", ""),
            "fixed_comment": payload.get("fixed_comment", ""),
            "language": payload.get("language", "fa"),
            "tone": payload.get("tone", "formal"),
            "skip_statuses": payload.get("skip_statuses") or [],
        },
        mode=payload.get("mode", "require_approval"),
        status="pending",
        total_count=preview["target_count"],
        idempotency_key=idempotency_key,
        correlation_id=payload["correlation_id"],
    )
    db.add(row)
    db.flush()
    for target in preview["targets"]:
        db.add(BulkOperationItem(bulk_operation_id=row.id, tenant_id=context.tenant_id, target_key=target))
    db.commit()
    db.refresh(row)
    return row


def start_bulk_job(bulk_id: int) -> int:
    return jobs.submit(
        "atlassian_bulk",
        f"Atlassian bulk operation #{bulk_id}",
        lambda: run_bulk(bulk_id),
        ref_type="bulk_operation",
        ref_id=bulk_id,
    )


def run_bulk(bulk_id: int) -> str:
    db = SessionLocal()
    try:
        bulk = db.get(BulkOperation, bulk_id)
        if bulk is None:
            return "Bulk operation no longer exists"
        connection = db.get(AtlassianConnection, bulk.connection_id)
        if connection is None:
            bulk.status = "failed"
            bulk.report = {"error": "Connection no longer exists"}
            db.commit()
            return "Connection no longer exists"
        context = AuthContext(username=bulk.owner_user_id, tenant_id=bulk.tenant_id, role="admin")
        bulk.status = "running"
        bulk.started_at = datetime.now(timezone.utc)
        db.commit()
        config = bulk.comment_config or {}
        items = db.query(BulkOperationItem).filter(
            BulkOperationItem.bulk_operation_id == bulk_id,
            BulkOperationItem.status.in_(["pending", "failed"]),
        ).order_by(BulkOperationItem.id).all()
        transport, provider = _providers(db, connection, bulk.product)
        try:
            cfg = llm.config_from_settings(get_all_resolved(db))
            block_closed = get_value(db, "atlassian_block_closed_issues", "true").lower() == "true"
            closed_names = {"closed", "done", "resolved", "cancelled", "canceled"}
            for item in items:
                db.refresh(bulk)
                if bulk.cancellation_requested:
                    bulk.status = "cancelled"
                    break
                while bulk.paused and not bulk.cancellation_requested:
                    time.sleep(0.5)
                    db.refresh(bulk)
                item.attempts += 1
                try:
                    context_data = provider.issue_context(item.target_key) if bulk.product == "jira" else provider.page_context(item.target_key)
                    status_name = str(context_data.get("status", "")).lower()
                    skip_statuses = {str(value).lower() for value in config.get("skip_statuses") or []}
                    if (block_closed and status_name in closed_names) or status_name in skip_statuses:
                        item.status = "skipped"
                        item.error_code = "policy_skip"
                        item.error_summary = f"Status '{context_data.get('status')}' is blocked by policy"
                        db.commit()
                        continue
                    if config.get("comment_mode") == "fixed":
                        comment = config.get("fixed_comment", "")
                    else:
                        comment = generate_comment(
                            context_data,
                            config.get("instruction") or "Provide a factual follow-up.",
                            config.get("language", "fa"),
                            config.get("tone", "formal"),
                            cfg,
                        ).text
                    previous = context_data.get("comments") or []
                    if is_similar_comment(comment, previous):
                        item.status = "skipped"
                        item.error_code = "duplicate_comment"
                        item.error_summary = "A similar comment already exists"
                        db.commit()
                        continue
                    item.preview_redacted = redact_text(db, comment)[:30000]
                    item.rendered_comment_hash = hashlib.sha256(comment.strip().encode()).hexdigest()
                    result = provider.add_comment(item.target_key, comment, bulk.correlation_id) if bulk.product == "jira" else provider.add_footer_comment(item.target_key, comment)
                    item.external_comment_id = str(result.get("id", ""))
                    item.status = "success"
                    item.error_code = ""
                    item.error_summary = ""
                except (AtlassianError, ValueError) as error:
                    item.status = "failed"
                    item.error_code = error.code if isinstance(error, AtlassianError) else "generation_error"
                    item.error_summary = str(error)[:700]
                db.commit()
                counts = {
                    status: db.query(BulkOperationItem).filter(
                        BulkOperationItem.bulk_operation_id == bulk_id,
                        BulkOperationItem.status == status,
                    ).count()
                    for status in ("success", "failed", "skipped")
                }
                bulk.success_count = counts["success"]
                bulk.failed_count = counts["failed"]
                bulk.skipped_count = counts["skipped"]
                completed = sum(counts.values())
                bulk.progress = int(completed * 100 / max(bulk.total_count, 1))
                db.commit()
                time.sleep(0.05)
        finally:
            transport.close()
        if bulk.status not in {"cancelled"}:
            bulk.status = "partial" if bulk.failed_count else "completed"
        bulk.progress = 100 if bulk.status in {"completed", "partial"} else bulk.progress
        bulk.finished_at = datetime.now(timezone.utc)
        failed_items = db.query(BulkOperationItem).filter(BulkOperationItem.bulk_operation_id == bulk_id, BulkOperationItem.status == "failed").all()
        bulk.report = {
            "success": bulk.success_count,
            "failed": bulk.failed_count,
            "skipped": bulk.skipped_count,
            "errors": [{"target": item.target_key, "code": item.error_code, "message": item.error_summary} for item in failed_items],
        }
        db.commit()
        record_history(
            db, context, connection_id=bulk.connection_id, product=bulk.product,
            operation_type="bulk_comment", query_type=bulk.target_type,
            query=str(bulk.target_spec), target_keys=[item.target_key for item in items],
            result_summary=f"success={bulk.success_count}, failed={bulk.failed_count}, skipped={bulk.skipped_count}",
            status="partial" if bulk.failed_count else "success", result_count=bulk.success_count,
            trace_id=bulk.correlation_id, metadata={"bulk_operation_id": bulk.id},
        )
        audit(
            db, context, "atlassian.bulk.comment", "bulk_operation", str(bulk.id),
            connection_id=bulk.connection_id, status=bulk.status, trace_id=bulk.correlation_id,
            details=bulk.report,
        )
        return f"{bulk.success_count} succeeded, {bulk.failed_count} failed, {bulk.skipped_count} skipped"
    finally:
        db.close()
