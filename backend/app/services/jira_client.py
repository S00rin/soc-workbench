"""Jira REST connector (Module 6). Supports Server/DC and Cloud.

Auth: Bearer PAT (Server/DC) or Basic email:token (Cloud). All write actions
go through a preview object first; the router asks the UI to confirm.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..logging_config import get_logger

logger = get_logger(__name__)


class JiraError(Exception):
    pass


@dataclass
class JiraConfig:
    base_url: str
    token: str = ""
    username: str = ""
    password: str = ""
    verify_ssl: bool = True
    timeout: int = 30

    @property
    def is_cloud(self) -> bool:
        return "atlassian.net" in self.base_url


class JiraClient:
    def __init__(self, cfg: JiraConfig):
        if not cfg.base_url:
            raise JiraError("Jira base URL is not configured.")
        self.cfg = cfg
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        auth = None
        if cfg.token and (cfg.is_cloud and cfg.username):
            auth = (cfg.username, cfg.token)  # Cloud: email + API token
        elif cfg.token:
            headers["Authorization"] = f"Bearer {cfg.token}"  # Server/DC PAT
        elif cfg.username and cfg.password:
            auth = (cfg.username, cfg.password)
        self._client = httpx.Client(
            base_url=cfg.base_url.rstrip("/"),
            headers=headers,
            auth=auth,
            verify=cfg.verify_ssl,
            timeout=cfg.timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "JiraClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _get(self, path: str, **params):
        try:
            r = self._client.get(path, params=params)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            raise JiraError(f"Jira {e.response.status_code}: {e.response.text[:300]}") from e
        except httpx.HTTPError as e:
            raise JiraError(f"Jira connection error: {e}") from e

    def _post(self, path: str, body: dict):
        try:
            r = self._client.post(path, json=body)
            r.raise_for_status()
            return r.json() if r.text else {}
        except httpx.HTTPStatusError as e:
            raise JiraError(f"Jira {e.response.status_code}: {e.response.text[:300]}") from e
        except httpx.HTTPError as e:
            raise JiraError(f"Jira connection error: {e}") from e

    # --- Read ---
    def test_connection(self) -> dict:
        data = self._get("/rest/api/2/myself")
        return {"ok": True, "user": data.get("displayName") or data.get("name")}

    def search(self, jql: str, max_results: int = 50, fields: list[str] | None = None) -> dict:
        fields = fields or [
            "summary", "status", "assignee", "priority", "created",
            "updated", "duedate", "labels", "project", "issuetype",
        ]
        return self._get(
            "/rest/api/2/search",
            jql=jql,
            maxResults=max_results,
            fields=",".join(fields),
        )

    def get_issue(self, key: str) -> dict:
        return self._get(f"/rest/api/2/issue/{key}", expand="changelog,renderedFields")

    def get_comments(self, key: str) -> dict:
        return self._get(f"/rest/api/2/issue/{key}/comment")

    def list_transitions(self, key: str) -> dict:
        return self._get(f"/rest/api/2/issue/{key}/transitions")

    # --- Write (each returns after a confirmed preview) ---
    def create_issue(self, fields: dict) -> dict:
        return self._post("/rest/api/2/issue", {"fields": fields})

    def add_comment(self, key: str, body: str) -> dict:
        return self._post(f"/rest/api/2/issue/{key}/comment", {"body": body})

    def transition(self, key: str, transition_id: str) -> dict:
        return self._post(
            f"/rest/api/2/issue/{key}/transitions",
            {"transition": {"id": transition_id}},
        )

    def update_issue(self, key: str, fields: dict) -> dict:
        try:
            r = self._client.put(f"/rest/api/2/issue/{key}", json={"fields": fields})
            r.raise_for_status()
            return {"ok": True}
        except httpx.HTTPStatusError as e:
            raise JiraError(f"Jira {e.response.status_code}: {e.response.text[:300]}") from e


def build_write_preview(action: str, target: str, fields: dict) -> dict:
    """Build the confirmation object shown in the UI before any write."""
    return {
        "action": action,          # create | comment | transition | update
        "target": target,          # issue key or project
        "fields": fields,
        "warning": "This will modify Jira. Confirm the exact fields before proceeding.",
    }


def summarize_issues(search_result: dict) -> dict:
    """Group/summarize issues for analysis (no LLM needed)."""
    issues = search_result.get("issues", [])
    by_status: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_assignee: dict[str, int] = {}
    unassigned = 0
    for it in issues:
        f = it.get("fields", {})
        status = (f.get("status") or {}).get("name", "Unknown")
        by_status[status] = by_status.get(status, 0) + 1
        pr = (f.get("priority") or {}).get("name", "None")
        by_priority[pr] = by_priority.get(pr, 0) + 1
        assignee = f.get("assignee")
        if assignee:
            name = assignee.get("displayName", "?")
            by_assignee[name] = by_assignee.get(name, 0) + 1
        else:
            unassigned += 1
    return {
        "total": search_result.get("total", len(issues)),
        "by_status": by_status,
        "by_priority": by_priority,
        "by_assignee": by_assignee,
        "unassigned": unassigned,
    }
