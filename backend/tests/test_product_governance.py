from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.config import get_settings
from app.models.governance import ExternalConnection, FeaturePolicy, IntegrationChatSession, UserAccount
from app.security import AuthContext
from app.services.access_control import (
    authenticate, hash_password, module_allowed, policy_state, seed_access_defaults, verify_password,
)
from app.services.integration_chat import _fallback_query, scoped_session
from app.services.wikijs_provider import (
    WikiJSError, WikiJSProvider, decrypt_wikijs_token, encrypt_wikijs_token, scoped_wikijs_connection,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_password_hash_authentication_and_module_rbac(db):
    encoded = hash_password("A-strong-temporary-password")
    assert "A-strong-temporary-password" not in encoded
    assert verify_password("A-strong-temporary-password", encoded)
    assert not verify_password("wrong-password", encoded)

    user = UserAccount(
        tenant_id="default", username="analyst-one", display_name="Analyst One",
        password_hash=encoded, role="analyst", module_permissions=["dashboard", "integrations"],
        active=True, must_change_password=True,
    )
    db.add(user)
    db.commit()
    assert authenticate(db, "analyst-one", "A-strong-temporary-password").id == user.id
    assert authenticate(db, "analyst-one", "wrong-password") is None
    assert module_allowed("analyst", user.module_permissions, "integrations")
    assert not module_allowed("analyst", user.module_permissions, "settings")
    assert module_allowed("admin", [], "settings")


def test_bootstrap_migration_preserves_legacy_short_admin_password(db):
    seed_access_defaults(db)
    row = db.query(UserAccount).filter(UserAccount.username == "admin").first()
    assert row is not None
    assert verify_password(get_settings().admin_password, row.password_hash)


def test_feature_policy_time_window_and_role_restriction():
    now = datetime.now(timezone.utc)
    scheduled = FeaturePolicy(enabled=True, starts_at=now + timedelta(hours=1), allowed_roles=[])
    assert policy_state(scheduled, now=now)["status"] == "scheduled"
    expired = FeaturePolicy(enabled=True, expires_at=now - timedelta(seconds=1), allowed_roles=[])
    assert policy_state(expired, now=now)["status"] == "expired"
    active = FeaturePolicy(enabled=True, starts_at=now - timedelta(hours=1), expires_at=now + timedelta(hours=1), allowed_roles=["admin"])
    assert policy_state(active, now=now)["active"] is True


def test_wikijs_token_is_encrypted_and_connections_are_tenant_scoped(db):
    row = ExternalConnection(
        tenant_id="tenant-a", owner_user_id="alice", provider="wikijs", name="Wiki",
        base_url="https://wiki.example.test", credentials_encrypted=encrypt_wikijs_token("wiki-secret-token"),
    )
    db.add(row)
    db.commit()
    assert "wiki-secret-token" not in row.credentials_encrypted
    assert decrypt_wikijs_token(row) == "wiki-secret-token"
    assert scoped_wikijs_connection(db, AuthContext("alice", "tenant-a", "admin"), row.id).id == row.id
    with pytest.raises(LookupError):
        scoped_wikijs_connection(db, AuthContext("mallory", "tenant-b", "admin"), row.id)


def test_wikijs_graphql_provider_lists_pages_and_classifies_permission(db):
    row = ExternalConnection(
        tenant_id="tenant-a", owner_user_id="alice", provider="wikijs", name="Wiki",
        base_url="https://wiki.example.test", credentials_encrypted=encrypt_wikijs_token("wiki-secret-token"),
        verify_ssl=True, timeout=10,
    )
    db.add(row)
    db.commit()

    def ok(request: httpx.Request):
        assert request.url.path == "/graphql"
        assert request.headers["Authorization"] == "Bearer wiki-secret-token"
        return httpx.Response(200, request=request, json={
            "data": {"pages": {"list": [{"id": 7, "path": "soc/runbook", "title": "SOC Runbook"}]}},
        })

    provider = WikiJSProvider(row, transport=httpx.MockTransport(ok), sleep=lambda _: None)
    try:
        assert provider.search_pages("runbook")[0]["id"] == 7
    finally:
        provider.close()

    def denied(request: httpx.Request):
        return httpx.Response(200, request=request, json={"errors": [{"message": "You do not have permission to view this page"}]})

    provider = WikiJSProvider(row, transport=httpx.MockTransport(denied), sleep=lambda _: None)
    try:
        with pytest.raises(WikiJSError) as captured:
            provider.list_pages()
        assert captured.value.code == "permission_denied"
        assert captured.value.action
    finally:
        provider.close()


def test_chat_history_is_owner_and_tenant_scoped(db):
    row = IntegrationChatSession(
        tenant_id="tenant-a", owner_user_id="alice", provider="jira", connection_id=10,
        title="Critical incidents",
    )
    db.add(row)
    db.commit()
    assert scoped_session(db, AuthContext("alice", "tenant-a", "analyst"), row.id).id == row.id
    with pytest.raises(LookupError):
        scoped_session(db, AuthContext("bob", "tenant-a", "analyst"), row.id)
    with pytest.raises(LookupError):
        scoped_session(db, AuthContext("alice", "tenant-b", "analyst"), row.id)


def test_prompt_fallbacks_remain_read_only_and_bounded():
    jira = _fallback_query("jira", "show open project SOC issues")
    assert "statusCategory != Done" in jira
    assert "ORDER BY updated DESC" in jira
    assert _fallback_query("confluence", "space=SEC recent pages").startswith("type = page")
    assert _fallback_query("splunk", "delete everything") == "search index=* | head 100"
