"""Connection ownership, legacy import and OAuth 2.0 (3LO) helpers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.atlassian import AtlassianConnection
from ..security import AuthContext
from .atlassian_credentials import encrypt_credentials, merge_credentials, validate_base_url
from .settings_service import get_value

DEFAULT_OAUTH_SCOPES = [
    "offline_access",
    "read:jira-work",
    "write:jira-work",
    "read:jira-user",
    "read:confluence-content.all",
    "write:confluence-content",
    "read:confluence-space.summary",
    "read:confluence-user",
]


def scoped_connection(db: Session, context: AuthContext, connection_id: int) -> AtlassianConnection:
    row = db.query(AtlassianConnection).filter(
        AtlassianConnection.id == connection_id,
        AtlassianConnection.tenant_id == context.tenant_id,
    ).first()
    if row is None:
        raise LookupError("Atlassian connection not found")
    return row


def safe_connection(row: AtlassianConnection) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "products": row.products,
        "deployment_type": row.deployment_type,
        "auth_type": row.auth_type,
        "base_url": row.base_url,
        "cloud_id": row.cloud_id,
        "username": row.username,
        "scopes": row.scopes,
        "verify_ssl": row.verify_ssl,
        "timeout": row.timeout,
        "enabled": row.enabled,
        "sorin_enabled": row.sorin_enabled,
        "auto_post_enabled": row.auto_post_enabled,
        "bulk_auto_post_enabled": row.bulk_auto_post_enabled,
        "has_credentials": bool(row.credentials_encrypted),
        "last_test_at": row.last_test_at,
        "last_success_at": row.last_success_at,
        "last_error_code": row.last_error_code,
        "last_error_summary": row.last_error_summary,
        "metadata": row.connection_metadata,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def seed_legacy_jira_connection(db: Session) -> None:
    """One-way, non-destructive import of the legacy Settings Jira connector."""
    if db.query(AtlassianConnection).count() > 0:
        return
    base_url = get_value(db, "jira_base_url")
    if not base_url:
        return
    token = get_value(db, "jira_token")
    password = get_value(db, "jira_password")
    username = get_value(db, "jira_username")
    cloud = "atlassian.net" in base_url
    auth_type = "api_token" if cloud and token else "pat" if token else "basic"
    credentials = {"api_token": token} if auth_type == "api_token" else {"pat": token} if auth_type == "pat" else {"password": password}
    row = AtlassianConnection(
        tenant_id=get_settings().default_tenant_id,
        owner_user_id=get_settings().admin_username,
        name="Legacy Jira",
        products=["jira"],
        deployment_type="cloud" if cloud else "data_center",
        auth_type=auth_type,
        base_url=validate_base_url(base_url),
        username=username,
        credentials_encrypted=encrypt_credentials(credentials),
        verify_ssl=get_value(db, "jira_verify_ssl", "true").lower() == "true",
        timeout=int(get_value(db, "jira_timeout", "30") or 30),
        connection_metadata={"migrated_from": "legacy_settings"},
    )
    db.add(row)
    db.commit()


def create_or_update(
    db: Session, context: AuthContext, payload: dict, row: AtlassianConnection | None = None,
) -> AtlassianConnection:
    if row is None:
        row = AtlassianConnection(tenant_id=context.tenant_id, owner_user_id=context.username)
    for key in (
        "name", "products", "deployment_type", "auth_type", "cloud_id", "username", "scopes",
        "verify_ssl", "timeout", "enabled", "sorin_enabled", "auto_post_enabled", "bulk_auto_post_enabled",
    ):
        if key in payload:
            setattr(row, key, payload[key])
    if "base_url" in payload:
        row.base_url = validate_base_url(payload["base_url"])
    credentials = payload.get("credentials") or {}
    if credentials:
        merge_credentials(row, credentials)
    if row.auth_type == "oauth2" and not row.scopes:
        row.scopes = DEFAULT_OAUTH_SCOPES
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _state_signature(data: bytes) -> str:
    digest = hmac.new(get_settings().secret_key.encode(), data, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def oauth_state(connection: AtlassianConnection, context: AuthContext) -> str:
    payload = {
        "connection_id": connection.id,
        "tenant_id": context.tenant_id,
        "user": context.username,
        "nonce": secrets.token_urlsafe(12),
        "expires": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
    }
    data = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{data}.{_state_signature(data.encode())}"


def parse_oauth_state(state: str) -> dict:
    try:
        data, signature = state.split(".", 1)
        if not hmac.compare_digest(signature, _state_signature(data.encode())):
            raise ValueError
        padded = data + "=" * (-len(data) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if int(payload["expires"]) < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError
        return payload
    except (ValueError, KeyError, json.JSONDecodeError) as error:
        raise ValueError("Invalid or expired OAuth state") from error


def oauth_authorization_url(connection: AtlassianConnection, context: AuthContext) -> str:
    settings = get_settings()
    if not settings.atlassian_oauth_client_id:
        raise ValueError("ATLASSIAN_OAUTH_CLIENT_ID is not configured")
    params = {
        "audience": "api.atlassian.com",
        "client_id": settings.atlassian_oauth_client_id,
        "scope": " ".join(connection.scopes or DEFAULT_OAUTH_SCOPES),
        "redirect_uri": settings.atlassian_oauth_redirect_uri,
        "state": oauth_state(connection, context),
        "response_type": "code",
        "prompt": "consent",
    }
    return f"https://auth.atlassian.com/authorize?{urlencode(params)}"


def oauth_callback(db: Session, code: str, state: str) -> AtlassianConnection:
    payload = parse_oauth_state(state)
    row = db.query(AtlassianConnection).filter(
        AtlassianConnection.id == int(payload["connection_id"]),
        AtlassianConnection.tenant_id == payload["tenant_id"],
    ).first()
    if row is None:
        raise ValueError("Atlassian connection no longer exists")
    settings = get_settings()
    response = httpx.post(
        "https://auth.atlassian.com/oauth/token",
        json={
            "grant_type": "authorization_code",
            "client_id": settings.atlassian_oauth_client_id,
            "client_secret": settings.atlassian_oauth_client_secret,
            "code": code,
            "redirect_uri": settings.atlassian_oauth_redirect_uri,
        },
        timeout=20,
    )
    response.raise_for_status()
    tokens = response.json()
    access_token = tokens["access_token"]
    resources = httpx.get(
        "https://api.atlassian.com/oauth/token/accessible-resources",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    resources.raise_for_status()
    sites = resources.json()
    preferred = next((site for site in sites if site.get("url", "").rstrip("/") == row.base_url.rstrip("/")), None)
    site = preferred or (sites[0] if sites else None)
    if not site:
        raise ValueError("OAuth succeeded but no accessible Atlassian site was returned")
    row.cloud_id = site["id"]
    row.base_url = site.get("url") or row.base_url
    row.connection_metadata = {**(row.connection_metadata or {}), "site_name": site.get("name", ""), "oauth_connected": True}
    row.credentials_encrypted = encrypt_credentials({
        "access_token": access_token,
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=int(tokens.get("expires_in", 3600)))).isoformat(),
    })
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
