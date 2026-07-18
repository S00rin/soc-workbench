"""Encrypted Atlassian credentials and OAuth refresh handling."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.atlassian import AtlassianConnection
from ..security import decrypt_secret, encrypt_secret


def validate_base_url(value: str) -> str:
    """Allow explicit HTTP(S) endpoints while rejecting credentials/fragments."""
    value = value.strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Base URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Base URL must not contain credentials or a fragment")
    return value


def encrypt_credentials(credentials: dict) -> str:
    clean = {key: value for key, value in credentials.items() if value not in (None, "")}
    return encrypt_secret(json.dumps(clean, ensure_ascii=False, separators=(",", ":")))


def decrypt_credentials(connection: AtlassianConnection) -> dict:
    if not connection.credentials_encrypted:
        return {}
    try:
        return json.loads(decrypt_secret(connection.credentials_encrypted) or "{}")
    except json.JSONDecodeError:
        return {}


def merge_credentials(connection: AtlassianConnection, updates: dict) -> None:
    current = decrypt_credentials(connection)
    for key, value in updates.items():
        if value not in (None, "", "********"):
            current[key] = value
    connection.credentials_encrypted = encrypt_credentials(current)


def oauth_access_token(db: Session, connection: AtlassianConnection) -> str:
    credentials = decrypt_credentials(connection)
    access_token = credentials.get("access_token", "")
    expires_at_raw = credentials.get("expires_at", "")
    expires_at = None
    if expires_at_raw:
        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
        except ValueError:
            expires_at = None
    if access_token and (expires_at is None or expires_at > datetime.now(timezone.utc) + timedelta(seconds=60)):
        return access_token

    refresh_token = credentials.get("refresh_token", "")
    settings = get_settings()
    client_id = credentials.get("client_id") or settings.atlassian_oauth_client_id
    client_secret = credentials.get("client_secret") or settings.atlassian_oauth_client_secret
    if not refresh_token or not client_id or not client_secret:
        raise ValueError("OAuth token expired; reconnect the Atlassian connection")

    response = httpx.post(
        "https://auth.atlassian.com/oauth/token",
        json={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
        timeout=20,
    )
    if response.status_code >= 400:
        raise ValueError("OAuth refresh failed; reauthorize the Atlassian connection")
    payload = response.json()
    credentials["access_token"] = payload["access_token"]
    # Atlassian uses rotating refresh tokens; always persist the returned one.
    credentials["refresh_token"] = payload.get("refresh_token") or refresh_token
    credentials["expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=int(payload.get("expires_in", 3600)))
    ).isoformat()
    connection.credentials_encrypted = encrypt_credentials(credentials)
    db.add(connection)
    db.commit()
    return credentials["access_token"]
