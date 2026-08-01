from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base
from app.models import AtlassianConnection
from app.security import AuthContext, decrypt_secret, require_admin
from app.services.sorin_comments import is_similar_comment
from app.services.atlassian_connections import create_or_update, scoped_connection
from app.services.atlassian_credentials import decrypt_credentials, encrypt_credentials, oauth_access_token, validate_base_url
from app.services.atlassian_http import AtlassianError, AtlassianTransport, classify_error
from app.services.confluence_provider import ConfluenceProvider
from app.services.field_mapping import preview_mapping, transform_value, validate_definition
from app.services.integration_history import record_history
from app.services.jira_provider import JiraProvider, adf_document, adf_to_text, jira_field_type
from app.models.atlassian import AtlassianFieldMapping, IdempotencyRecord, IntegrationHistory


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def context():
    return AuthContext(username="alice", tenant_id="tenant-a", role="admin")


def connection(db: Session, context: AuthContext, **overrides) -> AtlassianConnection:
    data = {
        "name": "Test Atlassian",
        "products": ["jira", "confluence"],
        "deployment_type": "cloud",
        "auth_type": "api_token",
        "base_url": "https://example.atlassian.net",
        "username": "alice@example.com",
        "credentials": {"api_token": "top-secret-token"},
        **overrides,
    }
    return create_or_update(db, context, data)


def test_connection_secrets_are_encrypted_and_scoped(db, context):
    row = connection(db, context)
    assert "top-secret-token" not in row.credentials_encrypted
    assert decrypt_credentials(row)["api_token"] == "top-secret-token"
    assert scoped_connection(db, context, row.id).id == row.id
    with pytest.raises(LookupError):
        scoped_connection(db, AuthContext("mallory", "tenant-b", "admin"), row.id)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com", "https://user:pass@example.com"])
def test_base_url_validation_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        validate_base_url(url)


def test_adf_round_trip_and_field_types():
    document = adf_document("First line\nSecond line")
    assert document["version"] == 1
    assert adf_to_text(document) == "First line\nSecond line"
    assert jira_field_type({"type": "array", "items": "component"}) == "components"
    assert jira_field_type({"type": "string", "custom": "com.atlassian.jira.plugin.system.customfieldtypes:textarea"}) == "rich_text"


def test_mapping_transformations_and_required_preview():
    assert transform_value("1, 2", {"op": "split", "separator": ","}) == ["1", "2"]
    assert transform_value("alice", {"op": "user"}, cloud=True) == {"accountId": "alice"}
    assert transform_value(["SOC"], {"op": "components"}) == [{"name": "SOC"}]
    errors = validate_definition(
        {"scope_type": "connection", "internal_type": "number", "transformation": {"op": "identity"}},
        {"type": "user", "read_only": False},
    )
    assert any("not directly compatible" in error for error in errors)

    row = AtlassianFieldMapping(
        tenant_id="tenant-a", owner_user_id="alice", connection_id=1,
        scope_type="connection", internal_field="title", internal_type="string",
        external_field_id="summary", external_field_name="Summary", external_type="string",
        transformation={"op": "identity"}, required=True,
    )
    preview = preview_mapping([row], {}, cloud=True)
    assert preview["valid"] is False
    assert "required" in preview["warnings"][0]


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [(401, "invalid_or_expired_token", False), (403, "permission_denied", False),
     (404, "not_found_or_restricted", False), (409, "conflict", False),
     (429, "rate_limited", True), (503, "upstream_error", True)],
)
def test_error_classification(status, code, retryable):
    request = httpx.Request("GET", "https://example.atlassian.net/rest/api/3/field")
    response = httpx.Response(status, request=request, text="failure")
    error = classify_error(response)
    assert error.code == code
    assert error.retryable is retryable


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("OAuth 2.0 scopes do not permit this operation", "insufficient_scope"),
        ("You do not have permission to add a comment", "comment_permission_denied"),
        ("Blocked by issue security level", "issue_security_denied"),
        ("Missing Browse Projects permission", "project_permission_denied"),
    ],
)
def test_permission_error_details_are_actionable(message, code):
    request = httpx.Request("POST", "https://example.atlassian.net/rest/api/3/issue/SOC-1/comment")
    response = httpx.Response(403, request=request, text=message)
    assert classify_error(response).code == code


def test_transport_retries_429_and_stops_on_401(db, context):
    row = connection(db, context)
    calls = {"count": 0}
    sleeps = []

    def handler(request: httpx.Request):
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, request=request, json={"error": "rate"})
        return httpx.Response(200, request=request, json={"ok": True})

    transport = AtlassianTransport(db, row, "jira", transport=httpx.MockTransport(handler), sleep=sleeps.append)
    try:
        assert transport.request("GET", "/rest/api/3/myself") == {"ok": True}
        assert calls["count"] == 2
        assert len(sleeps) == 1
    finally:
        transport.close()

    def unauthorized(request: httpx.Request):
        return httpx.Response(401, request=request, json={"error": "bad token"})

    transport = AtlassianTransport(db, row, "jira", transport=httpx.MockTransport(unauthorized), sleep=sleeps.append)
    try:
        with pytest.raises(AtlassianError) as captured:
            transport.request("GET", "/rest/api/3/myself")
        assert captured.value.code == "invalid_or_expired_token"
    finally:
        transport.close()


def test_oauth_refresh_rotates_and_persists_token(db, context, monkeypatch):
    row = connection(db, context, auth_type="oauth2", credentials={})
    row.credentials_encrypted = encrypt_credentials({
        "access_token": "expired-access",
        "refresh_token": "old-refresh",
        "expires_at": "2000-01-01T00:00:00+00:00",
        "client_id": "client-id",
        "client_secret": "client-secret",
    })
    db.commit()

    def refresh(url, json, timeout):
        assert json["refresh_token"] == "old-refresh"
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600})

    monkeypatch.setattr("app.services.atlassian_credentials.httpx.post", refresh)
    assert oauth_access_token(db, row) == "new-access"
    assert decrypt_credentials(row)["refresh_token"] == "new-refresh"


def test_rbac_and_idempotency_are_tenant_scoped(db, context):
    assert require_admin(context) == context
    with pytest.raises(HTTPException) as denied:
        require_admin(AuthContext("bob", "tenant-a", "analyst"))
    assert getattr(denied.value, "status_code", None) == 403

    db.add(IdempotencyRecord(tenant_id="tenant-a", scope="jira-comment:1", key="request-1", request_hash="a", response={}))
    db.commit()
    db.add(IdempotencyRecord(tenant_id="tenant-b", scope="jira-comment:1", key="request-1", request_hash="b", response={}))
    db.commit()
    db.add(IdempotencyRecord(tenant_id="tenant-a", scope="jira-comment:1", key="request-1", request_hash="different", response={}))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

def test_dynamic_custom_fields_and_cloud_adf_comment(db, context):
    row = connection(db, context)
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        if request.url.path.endswith("/field"):
            return httpx.Response(200, request=request, json=[
                {"id": "summary", "name": "Summary", "custom": False, "orderable": True, "schema": {"type": "string"}},
                {"id": "customfield_10042", "name": "Risk", "custom": True, "orderable": True, "schema": {"type": "option", "custom": "select"}},
            ])
        if request.url.path.endswith("/comment") and request.method == "POST":
            body = json.loads(request.content)
            assert body["body"]["type"] == "doc"
            assert body["properties"][0]["key"] == "soc-workbench.audit"
            return httpx.Response(201, request=request, json={"id": "77"})
        raise AssertionError(request.url)

    transport = AtlassianTransport(db, row, "jira", transport=httpx.MockTransport(handler), sleep=lambda _: None)
    provider = JiraProvider(transport, cloud=True)
    try:
        fields = provider.list_fields()
        assert {item["id"] for item in fields} == {"summary", "customfield_10042"}
        assert next(item for item in fields if item["custom"])["type"] == "select"
        assert provider.add_comment("SOC-1", "Factual update", "trace-1")["id"] == "77"
    finally:
        transport.close()


def test_confluence_cloud_spaces_and_page_context(db, context):
    row = connection(db, context)

    def handler(request: httpx.Request):
        if request.url.path.endswith("/spaces"):
            return httpx.Response(200, request=request, json={"results": [{"id": "1", "key": "SOC"}]})
        if request.url.path.endswith("/pages/10"):
            return httpx.Response(200, request=request, json={"id": "10", "title": "Runbook", "status": "current", "body": {"storage": {"value": "<p>Only factual content.</p>"}}})
        if request.url.path.endswith("/footer-comments"):
            return httpx.Response(200, request=request, json={"results": []})
        raise AssertionError(request.url)

    transport = AtlassianTransport(db, row, "confluence", transport=httpx.MockTransport(handler), sleep=lambda _: None)
    provider = ConfluenceProvider(transport, cloud=True)
    try:
        assert provider.list_spaces()[0]["key"] == "SOC"
        assert provider.page_context("10")["content"] == "Only factual content."
    finally:
        transport.close()


def test_history_redacts_tokens_and_is_tenant_owned(db, context):
    row = record_history(
        db, context, connection_id=None, product="jira", operation_type="search",
        query_type="jql", query="token=super-secret-value and reporter=admin@example.com",
        status="success", trace_id="trace-history",
    )
    assert "super-secret-value" not in row.query_redacted
    assert "admin@example.com" not in row.query_redacted
    assert row.tenant_id == "tenant-a"
    assert db.query(IntegrationHistory).filter(IntegrationHistory.tenant_id == "tenant-b").count() == 0


def test_duplicate_comment_similarity():
    assert is_similar_comment("Please confirm the next action.", ["Please confirm the next action!"])
    assert not is_similar_comment("Contain the affected host.", ["Please confirm the next action."])


@pytest.mark.skipif(not os.getenv("ATLASSIAN_TEST_URL"), reason="optional live integration test")
def test_optional_live_connection():
    base_url = validate_base_url(os.environ["ATLASSIAN_TEST_URL"])
    assert base_url.startswith("https://")
