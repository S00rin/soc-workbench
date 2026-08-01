"""Users, feature entitlements, external integrations and shared chat history."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import TimestampMixin


class UserAccount(Base, TimestampMixin):
    __tablename__ = "user_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="uq_user_account_tenant_username"),
        Index("ix_user_account_tenant_active", "tenant_id", "active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), default="default", index=True)
    username: Mapped[str] = mapped_column(String(120), index=True)
    display_name: Mapped[str] = mapped_column(String(180), default="")
    email: Mapped[str] = mapped_column(String(240), default="")
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(40), default="analyst", index=True)
    module_permissions: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FeaturePolicy(Base, TimestampMixin):
    __tablename__ = "feature_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "feature_key", name="uq_feature_policy_tenant_key"),
        Index("ix_feature_policy_expiry", "tenant_id", "enabled", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), default="default", index=True)
    feature_key: Mapped[str] = mapped_column(String(100), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    allowed_roles: Mapped[list] = mapped_column(JSON, default=list)
    policy_config: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_by: Mapped[str] = mapped_column(String(120), default="")


class ExternalConnection(Base, TimestampMixin):
    __tablename__ = "external_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", "name", name="uq_external_connection_tenant_provider_name"),
        Index("ix_external_connection_scope", "tenant_id", "provider", "enabled"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), default="default", index=True)
    owner_user_id: Mapped[str] = mapped_column(String(120), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(160))
    base_url: Mapped[str] = mapped_column(String(500))
    credentials_encrypted: Mapped[str] = mapped_column(Text, default="")
    verify_ssl: Mapped[bool] = mapped_column(Boolean, default=True)
    timeout: Mapped[int] = mapped_column(Integer, default=30)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sorin_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str] = mapped_column(String(80), default="")
    last_error_summary: Mapped[str] = mapped_column(Text, default="")
    connection_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class IntegrationChatSession(Base, TimestampMixin):
    __tablename__ = "integration_chat_sessions"
    __table_args__ = (Index("ix_chat_session_owner", "tenant_id", "owner_user_id", "updated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), default="default", index=True)
    owner_user_id: Mapped[str] = mapped_column(String(120), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    connection_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(240), default="New integration chat")
    scope_query: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)


class IntegrationChatTurn(Base, TimestampMixin):
    __tablename__ = "integration_chat_turns"
    __table_args__ = (Index("ix_chat_turn_session", "session_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("integration_chat_sessions.id", ondelete="CASCADE"), index=True)
    tenant_id: Mapped[str] = mapped_column(String(80), default="default", index=True)
    owner_user_id: Mapped[str] = mapped_column(String(120), index=True)
    prompt_redacted: Mapped[str] = mapped_column(Text)
    generated_query: Mapped[str] = mapped_column(Text, default="")
    query_language: Mapped[str] = mapped_column(String(30), default="")
    response_markdown: Mapped[str] = mapped_column(Text, default="")
    result_data: Mapped[dict] = mapped_column(JSON, default=dict)
    provider_name: Mapped[str] = mapped_column(String(80), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(30), default="success", index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str] = mapped_column(String(80), default="")
    error_summary: Mapped[str] = mapped_column(Text, default="")
    correlation_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)


class UserActivity(Base, TimestampMixin):
    __tablename__ = "user_activity"
    __table_args__ = (Index("ix_user_activity_filter", "tenant_id", "actor_user_id", "module_key", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(80), default="default", index=True)
    actor_user_id: Mapped[str] = mapped_column(String(120), index=True)
    module_key: Mapped[str] = mapped_column(String(80), default="general", index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    method: Mapped[str] = mapped_column(String(12), default="")
    path: Mapped[str] = mapped_column(String(500), default="")
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
