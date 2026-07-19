"""Wiki.js GraphQL provider with encrypted credentials and classified errors."""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
from sqlalchemy.orm import Session

from ..models.governance import ExternalConnection
from ..security import AuthContext, decrypt_secret, encrypt_secret
from .atlassian_credentials import validate_base_url
from .atlassian_http import redact_error


@dataclass
class WikiJSError(Exception):
    code: str
    message: str
    status_code: int = 0
    retryable: bool = False
    action: str = ""

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "status_code": self.status_code,
            "retryable": self.retryable,
            "action": self.action,
        }


def encrypt_wikijs_token(token: str) -> str:
    return encrypt_secret(json.dumps({"api_token": token.strip()}, separators=(",", ":")))


def decrypt_wikijs_token(connection: ExternalConnection) -> str:
    if not connection.credentials_encrypted:
        return ""
    try:
        return str(json.loads(decrypt_secret(connection.credentials_encrypted) or "{}").get("api_token") or "")
    except (json.JSONDecodeError, TypeError):
        return ""


def safe_external_connection(row: ExternalConnection) -> dict:
    return {
        "id": row.id,
        "provider": row.provider,
        "name": row.name,
        "base_url": row.base_url,
        "verify_ssl": row.verify_ssl,
        "timeout": row.timeout,
        "enabled": row.enabled,
        "ai_enabled": row.ai_enabled,
        "has_credentials": bool(row.credentials_encrypted),
        "last_test_at": row.last_test_at,
        "last_success_at": row.last_success_at,
        "last_error_code": row.last_error_code,
        "last_error_summary": row.last_error_summary,
        "metadata": row.connection_metadata or {},
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def scoped_wikijs_connection(db: Session, context: AuthContext, connection_id: int) -> ExternalConnection:
    row = db.query(ExternalConnection).filter(
        ExternalConnection.id == connection_id,
        ExternalConnection.tenant_id == context.tenant_id,
        ExternalConnection.provider == "wikijs",
    ).first()
    if row is None:
        raise LookupError("Wiki.js connection not found")
    return row


def upsert_wikijs_connection(
    db: Session, context: AuthContext, payload: dict, row: ExternalConnection | None = None,
) -> ExternalConnection:
    if row is None:
        row = ExternalConnection(
            tenant_id=context.tenant_id,
            owner_user_id=context.username,
            provider="wikijs",
        )
    if "name" in payload:
        row.name = payload["name"].strip()
    if "base_url" in payload:
        row.base_url = validate_base_url(payload["base_url"])
    for key in ("verify_ssl", "timeout", "enabled", "ai_enabled"):
        if key in payload:
            setattr(row, key, payload[key])
    token = str(payload.get("api_token") or "").strip()
    if token and token != "********":
        row.credentials_encrypted = encrypt_wikijs_token(token)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _classify_response(response: httpx.Response) -> WikiJSError:
    status = response.status_code
    if status == 401:
        return WikiJSError("invalid_or_expired_token", "Wiki.js API token is invalid or expired.", status, False, "Create a new API key in Wiki.js Administration > API Access.")
    if status == 403:
        return WikiJSError("permission_denied", "The Wiki.js API token lacks the required page permission.", status, False, "Grant the token group read access to the target pages and locale.")
    if status == 404:
        return WikiJSError("graphql_endpoint_not_found", "The Wiki.js GraphQL endpoint was not found.", status, False, "Verify the Wiki.js base URL and that API Access is enabled.")
    if status == 429:
        return WikiJSError("rate_limited", "Wiki.js rate limit was reached.", status, True, "Wait and retry the request.")
    if status >= 500:
        return WikiJSError("upstream_error", "Wiki.js is temporarily unavailable.", status, True, "Retry after the server recovers.")
    return WikiJSError("wikijs_api_error", f"Wiki.js rejected the request. {redact_error(response.text)[:220]}", status)


class WikiJSProvider:
    LIST_QUERY = """
        query SocWorkbenchPageList {
          pages { list(orderBy: TITLE) { id path title } }
        }
    """
    PAGE_QUERY = """
        query SocWorkbenchPage($id: Int!) {
          pages { single(id: $id) { id path title description content createdAt updatedAt } }
        }
    """

    def __init__(
        self,
        connection: ExternalConnection,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
    ):
        self.connection = connection
        self.sleep = sleep
        self.max_attempts = max(1, max_attempts)
        token = decrypt_wikijs_token(connection)
        if not token:
            raise WikiJSError("missing_token", "Wiki.js API token is not configured.", action="Add an API token to this connection.")
        self.client = httpx.Client(
            base_url=connection.base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            verify=connection.verify_ssl,
            timeout=max(5, min(connection.timeout, 120)),
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def graphql(self, document: str, variables: dict | None = None) -> dict:
        last_error: WikiJSError | None = None
        for attempt in range(self.max_attempts):
            try:
                response = self.client.post("/graphql", json={"query": document, "variables": variables or {}})
            except httpx.HTTPError as error:
                last_error = WikiJSError("network_error", "Could not reach Wiki.js.", 0, True, "Check the URL, TLS certificate, DNS and firewall.")
                if attempt + 1 >= self.max_attempts:
                    raise last_error from error
            else:
                if response.status_code >= 400:
                    last_error = _classify_response(response)
                    if not last_error.retryable or attempt + 1 >= self.max_attempts:
                        raise last_error
                else:
                    try:
                        payload = response.json()
                    except ValueError as error:
                        raise WikiJSError("invalid_response", "Wiki.js returned invalid JSON.") from error
                    errors = payload.get("errors") or []
                    if errors:
                        raw = redact_error("; ".join(str(item.get("message") or "GraphQL error") for item in errors))
                        lowered = raw.lower()
                        code = "permission_denied" if any(word in lowered for word in ("permission", "unauthorized", "forbidden")) else "graphql_error"
                        action = "Grant the token group read access to the target pages." if code == "permission_denied" else "Check Wiki.js API logs and schema compatibility."
                        raise WikiJSError(code, raw[:500], 200, False, action)
                    return payload.get("data") or {}
            if last_error and last_error.retryable:
                self.sleep(min(4.0, (2**attempt) + random.random()))
        raise last_error or WikiJSError("unknown_error", "Wiki.js request failed.")

    def list_pages(self, limit: int = 100) -> list[dict]:
        pages = ((self.graphql(self.LIST_QUERY).get("pages") or {}).get("list") or [])
        return [
            {"id": item.get("id"), "path": item.get("path", ""), "title": item.get("title", "")}
            for item in pages[: max(1, min(limit, 500))]
        ]

    def search_pages(self, query: str, limit: int = 50) -> list[dict]:
        terms = [term.casefold() for term in query.split() if len(term.strip()) > 1]
        pages = self.list_pages(500)
        if not terms:
            return pages[:limit]
        ranked: list[tuple[int, dict]] = []
        for page in pages:
            haystack = f"{page.get('title', '')} {page.get('path', '')}".casefold()
            score = sum(1 for term in terms if term in haystack)
            if score:
                ranked.append((score, page))
        ranked.sort(key=lambda item: (-item[0], str(item[1].get("title", ""))))
        return [page for _, page in ranked[: max(1, min(limit, 100))]]

    def get_page(self, page_id: int) -> dict:
        page = ((self.graphql(self.PAGE_QUERY, {"id": int(page_id)}).get("pages") or {}).get("single") or {})
        if not page:
            raise WikiJSError("page_not_found", "Wiki.js page was not found.", 404, False, "Verify the page id and token permissions.")
        return page

    def capability_preflight(self) -> dict:
        try:
            pages = self.list_pages(3)
            return {
                "can_connect": {"allowed": True},
                "can_read_pages": {"allowed": True, "detail": {"sample_count": len(pages)}},
                "can_search_pages": {"allowed": True, "detail": "Title and path search is available."},
            }
        except WikiJSError as error:
            return {
                "can_connect": {"allowed": False, "error": error.as_dict()},
                "can_read_pages": {"allowed": False, "error": error.as_dict()},
                "can_search_pages": {"allowed": False, "error": error.as_dict()},
            }


def update_test_state(db: Session, row: ExternalConnection, capabilities: dict) -> None:
    row.last_test_at = datetime.now(timezone.utc)
    success = bool((capabilities.get("can_connect") or {}).get("allowed"))
    if success:
        row.last_success_at = row.last_test_at
        row.last_error_code = ""
        row.last_error_summary = ""
    else:
        error = (capabilities.get("can_connect") or {}).get("error") or {}
        row.last_error_code = str(error.get("code") or "connection_failed")[:80]
        row.last_error_summary = str(error.get("message") or "Connection failed")[:700]
    db.add(row)
    db.commit()
