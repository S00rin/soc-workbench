"""Persistent Atlassian integration domain models.

All user-owned rows carry both tenant and owner identifiers. SOC Workbench is
currently single-user, but the explicit ownership boundary prevents a future
multi-tenant deployment from accidentally exposing global records.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import TimestampMixin


class AtlassianConnection(Base, TimestampMixin):
    __tablename__ = "atlassian_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_atlassian_connection_tenant_name"),
        Index("ix_atlassian_connection_owner", "tenant_id", "owner_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), default="default", index=True)
    owner_user_id: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(160))
    products: Mapped[list] = mapped_column(JSON, default=list)
    deployment_type: Mapped[str] = mapped_column(String(30), default="cloud")
    auth_type: Mapped[str] = mapped_column(String(30), default="api_token")
    base_url: Mapped[str] = mapped_column(String(500))
    cloud_id: Mapped[str] = mapped_column(String(120), default="")
    username: Mapped[str] = mapped_column(String(240), default="")
    credentials_encrypted: Mapped[str] = mapped_column(Text, default="")
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    verify_ssl: Mapped[bool] = mapped_column(Boolean, default=True)
    timeout: Mapped[int] = mapped_column(Integer, default=30)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_post_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    bulk_auto_post_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str] = mapped_column(String(80), default="")
    last_error_summary: Mapped[str] = mapped_column(Text, default="")
    connection_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class AtlassianFieldMapping(Base, TimestampMixin):
    __tablename__ = "atlassian_field_mappings"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "scope_type", "project_key", "issue_type_id", "internal_field",
            name="uq_atlassian_mapping_scope_internal",
        ),
        Index("ix_atlassian_mapping_scope", "tenant_id", "connection_id", "scope_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), default="default", index=True)
    owner_user_id: Mapped[str] = mapped_column(String(120), index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("atlassian_connections.id", ondelete="CASCADE"), index=True)
    product: Mapped[str] = mapped_column(String(30), default="jira")
    scope_type: Mapped[str] = mapped_column(String(30), default="connection")
    project_key: Mapped[str] = mapped_column(String(80), default="")
    issue_type_id: Mapped[str] = mapped_column(String(80), default="")
    internal_field: Mapped[str] = mapped_column(String(160))
    internal_type: Mapped[str] = mapped_column(String(40), default="string")
    external_field_id: Mapped[str] = mapped_column(String(160))
    external_field_name: Mapped[str] = mapped_column(String(240), default="")
    external_type: Mapped[str] = mapped_column(String(40), default="string")
    external_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    transformation: Mapped[dict] = mapped_column(JSON, default=dict)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    read_only: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="valid", index=True)
    validation_message: Mapped[str] = mapped_column(Text, default="")
    metadata_version: Mapped[str] = mapped_column(String(120), default="")
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntegrationHistory(Base, TimestampMixin):
    __tablename__ = "integration_history"
    __table_args__ = (
        Index("ix_integration_history_filter", "tenant_id", "product", "operation_type", "status", "created_at"),
        Index("ix_integration_history_issue", "tenant_id", "connection_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), default="default", index=True)
    owner_user_id: Mapped[str] = mapped_column(String(120), index=True)
    connection_id: Mapped[int | None] = mapped_column(ForeignKey("atlassian_connections.id", ondelete="SET NULL"), nullable=True)
    product: Mapped[str] = mapped_column(String(30), index=True)
    operation_type: Mapped[str] = mapped_column(String(60), index=True)
    query_type: Mapped[str] = mapped_column(String(60), default="")
    prompt_redacted: Mapped[str] = mapped_column(Text, default="")
    query_redacted: Mapped[str] = mapped_column(Text, default="")
    final_query: Mapped[str] = mapped_column(Text, default="")
    target_keys: Mapped[list] = mapped_column(JSON, default=list)
    project_key: Mapped[str] = mapped_column(String(80), default="", index=True)
    result_summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str] = mapped_column(String(80), default="")
    error_summary: Mapped[str] = mapped_column(Text, default="")
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str] = mapped_column(String(80), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    correlation_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    history_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_scope", "tenant_id", "action", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), default="default", index=True)
    actor_user_id: Mapped[str] = mapped_column(String(120), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(80), default="")
    resource_id: Mapped[str] = mapped_column(String(160), default="")
    connection_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="success")
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class BulkOperation(Base, TimestampMixin):
    __tablename__ = "bulk_operations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_bulk_tenant_idempotency"),
        Index("ix_bulk_scope_status", "tenant_id", "owner_user_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), default="default", index=True)
    owner_user_id: Mapped[str] = mapped_column(String(120), index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("atlassian_connections.id", ondelete="CASCADE"), index=True)
    product: Mapped[str] = mapped_column(String(30), default="jira")
    operation_type: Mapped[str] = mapped_column(String(60), default="comment")
    target_type: Mapped[str] = mapped_column(String(40), default="issue_keys")
    target_spec: Mapped[dict] = mapped_column(JSON, default=dict)
    comment_config: Mapped[dict] = mapped_column(JSON, default=dict)
    mode: Mapped[str] = mapped_column(String(40), default="require_approval")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(120))
    correlation_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report: Mapped[dict] = mapped_column(JSON, default=dict)


class BulkOperationItem(Base, TimestampMixin):
    __tablename__ = "bulk_operation_items"
    __table_args__ = (
        UniqueConstraint("bulk_operation_id", "target_key", name="uq_bulk_item_target"),
        Index("ix_bulk_item_status", "bulk_operation_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bulk_operation_id: Mapped[int] = mapped_column(ForeignKey("bulk_operations.id", ondelete="CASCADE"), index=True)
    tenant_id: Mapped[str] = mapped_column(String(80), default="default", index=True)
    target_key: Mapped[str] = mapped_column(String(160))
    target_url: Mapped[str] = mapped_column(String(700), default="")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    preview_redacted: Mapped[str] = mapped_column(Text, default="")
    rendered_comment_hash: Mapped[str] = mapped_column(String(80), default="", index=True)
    external_comment_id: Mapped[str] = mapped_column(String(160), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str] = mapped_column(String(80), default="")
    error_summary: Mapped[str] = mapped_column(Text, default="")


class IdempotencyRecord(Base, TimestampMixin):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("tenant_id", "scope", "key", name="uq_idempotency_tenant_scope_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), default="default", index=True)
    scope: Mapped[str] = mapped_column(String(80), index=True)
    key: Mapped[str] = mapped_column(String(160))
    request_hash: Mapped[str] = mapped_column(String(80))
    response: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class AtlassianContentLink(Base, TimestampMixin):
    __tablename__ = "atlassian_content_links"
    __table_args__ = (UniqueConstraint("connection_id", "jira_issue_key", "confluence_page_id", name="uq_atlassian_content_link"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), default="default", index=True)
    owner_user_id: Mapped[str] = mapped_column(String(120), index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("atlassian_connections.id", ondelete="CASCADE"), index=True)
    jira_issue_key: Mapped[str] = mapped_column(String(80), index=True)
    confluence_page_id: Mapped[str] = mapped_column(String(120), index=True)
    relation_type: Mapped[str] = mapped_column(String(40), default="related")
