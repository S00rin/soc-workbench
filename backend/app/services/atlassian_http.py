"""Shared resilient HTTP transport for Jira and Confluence providers."""
from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx
from sqlalchemy.orm import Session

from ..models.atlassian import AtlassianConnection
from .atlassian_credentials import decrypt_credentials, oauth_access_token


SECRET_PATTERN = re.compile(
    r"(?i)(authorization|api[_-]?token|access[_-]?token|refresh[_-]?token|password|cookie)"
    r"\s*[:=]\s*([^\s,;]+)"
)


def redact_error(value: str) -> str:
    return SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)[:700]


@dataclass
class AtlassianError(Exception):
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


def classify_error(response: httpx.Response) -> AtlassianError:
    status = response.status_code
    raw = redact_error(response.text or "")
    lower = raw.lower()
    if status == 401:
        return AtlassianError("invalid_or_expired_token", "Credential is invalid or expired.", status, False, "Reconnect or update the credential.")
    if status == 403:
        if "scope" in lower or "oauth 2.0 scopes" in lower:
            return AtlassianError("insufficient_scope", "The credential does not include the required Atlassian scope.", status, False, "Reauthorize with the required scopes.")
        if "comment" in lower:
            return AtlassianError("comment_permission_denied", "The user cannot add a comment to this resource.", status, False, "Grant Add Comments or space comment permission and check the item workflow/policy.")
        if "issue security" in lower or "security level" in lower:
            return AtlassianError("issue_security_denied", "Issue security hides or restricts this issue.", status, False, "Add the service account to the applicable issue security level.")
        if "project" in lower or "browse projects" in lower:
            return AtlassianError("project_permission_denied", "The authenticated user lacks the required Jira project permission.", status, False, "Grant Browse Projects and the operation-specific project permission.")
        return AtlassianError("permission_denied", "The authenticated user lacks permission for this resource.", status, False, "Check project/space permission, comment permission, and issue security.")
    if status == 404:
        return AtlassianError("not_found_or_restricted", "The resource was not found or is hidden by issue/content security.", status, False, "Verify the key/id and Browse/View permission.")
    if status == 409:
        return AtlassianError("conflict", "Atlassian rejected the operation because the resource changed.", status, False, "Reload metadata and retry the operation.")
    if status == 429:
        return AtlassianError("rate_limited", "Atlassian rate limit was reached.", status, True, "Wait for Retry-After before retrying.")
    if status >= 500:
        return AtlassianError("upstream_error", "Atlassian is temporarily unavailable.", status, True, "Retry later; the operation was not treated as successful.")
    message = "Atlassian rejected the request."
    if raw:
        message = f"{message} {raw[:250]}"
    return AtlassianError("jira_api_error" if "/jira" in str(response.url) else "atlassian_api_error", message, status)


class AtlassianTransport:
    def __init__(
        self,
        db: Session,
        connection: AtlassianConnection,
        product: str,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
    ):
        self.connection = connection
        self.product = product
        self.sleep = sleep
        self.max_attempts = max(1, max_attempts)
        credentials = decrypt_credentials(connection)
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        auth = None
        if connection.auth_type == "oauth2":
            token = oauth_access_token(db, connection)
            headers["Authorization"] = f"Bearer {token}"
        elif connection.auth_type == "api_token":
            auth = (connection.username, credentials.get("api_token", ""))
        elif connection.auth_type == "pat":
            headers["Authorization"] = f"Bearer {credentials.get('pat', '')}"
        elif connection.auth_type == "basic":
            auth = (connection.username, credentials.get("password", ""))

        if connection.auth_type == "oauth2" and connection.cloud_id:
            base_url = f"https://api.atlassian.com/ex/{product}/{connection.cloud_id}"
        else:
            base_url = connection.base_url.rstrip("/")
        self.client = httpx.Client(
            base_url=base_url,
            headers=headers,
            auth=auth,
            verify=connection.verify_ssl,
            timeout=connection.timeout,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "AtlassianTransport":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def request(self, method: str, path: str, **kwargs: Any) -> dict:
        last_error: AtlassianError | None = None
        for attempt in range(self.max_attempts):
            try:
                response = self.client.request(method, path, **kwargs)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = AtlassianError("network_error", "Could not reach Atlassian.", 0, True, "Check DNS, proxy, TLS and the base URL.")
                if attempt + 1 >= self.max_attempts:
                    raise last_error from exc
                self.sleep(min(4.0, 0.4 * (2**attempt)) + random.uniform(0, 0.15))
                continue
            if response.status_code < 400:
                if response.status_code == 204 or not response.content:
                    return {}
                return response.json()
            last_error = classify_error(response)
            if not last_error.retryable or attempt + 1 >= self.max_attempts:
                raise last_error
            retry_after = response.headers.get("Retry-After", "")
            try:
                delay = min(float(retry_after), 15.0) if retry_after else min(4.0, 0.5 * (2**attempt))
            except ValueError:
                delay = min(4.0, 0.5 * (2**attempt))
            self.sleep(delay + random.uniform(0, 0.15))
        raise last_error or AtlassianError("unknown", "Unknown Atlassian error")
