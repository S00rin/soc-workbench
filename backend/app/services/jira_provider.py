"""Jira Cloud/Data Center provider with dynamic metadata and ADF support."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .atlassian_http import AtlassianError, AtlassianTransport


def adf_document(text: str) -> dict:
    """Convert plain text to a minimal valid Atlassian Document Format body."""
    paragraphs = []
    for line in (text or "").splitlines() or [""]:
        content = [{"type": "text", "text": line}] if line else []
        paragraphs.append({"type": "paragraph", "content": content})
    return {"version": 1, "type": "doc", "content": paragraphs}


def adf_to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    parts: list[str] = []
    stack: list[Any] = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("type") == "text" and isinstance(node.get("text"), str):
                parts.append(node["text"])
            stack.extend(reversed(node.get("content") or []))
        elif isinstance(node, list):
            stack.extend(reversed(node))
    return "\n".join(part for part in parts if part)


def jira_field_type(schema: dict) -> str:
    raw_type = (schema or {}).get("type", "string")
    custom = (schema or {}).get("custom", "")
    items = (schema or {}).get("items", "")
    if raw_type in {"number", "integer"}:
        return "number"
    if raw_type in {"date", "datetime"}:
        return "datetime" if raw_type == "datetime" else "date"
    if raw_type == "array":
        if items == "string":
            return "labels"
        if items == "component":
            return "components"
        return "multi_select"
    if raw_type == "user":
        return "user"
    if raw_type == "group":
        return "group"
    if raw_type in {"priority", "status"}:
        return raw_type
    if "textarea" in custom:
        return "rich_text"
    if "select" in custom:
        return "select"
    return "string"


class JiraProvider:
    def __init__(self, transport: AtlassianTransport, cloud: bool):
        self.transport = transport
        self.cloud = cloud
        self.api = "/rest/api/3" if cloud else "/rest/api/2"

    def myself(self) -> dict:
        return self.transport.request("GET", f"{self.api}/myself")

    def list_projects(self, limit: int = 50) -> list[dict]:
        if self.cloud:
            data = self.transport.request("GET", f"{self.api}/project/search", params={"maxResults": min(limit, 100)})
            return data.get("values", [])
        data = self.transport.request("GET", f"{self.api}/project")
        return data[:limit] if isinstance(data, list) else []

    def list_fields(self, project_key: str = "", issue_type_id: str = "") -> list[dict]:
        fields = self.transport.request("GET", f"{self.api}/field")
        required: dict[str, bool] = {}
        readonly: dict[str, bool] = {}
        if project_key and issue_type_id:
            try:
                if self.cloud:
                    metadata = self.transport.request(
                        "GET", f"{self.api}/issue/createmeta/{project_key}/issuetypes/{issue_type_id}",
                        params={"maxResults": 200},
                    )
                    for item in metadata.get("values", []):
                        required[item.get("fieldId", "")] = bool(item.get("required"))
                else:
                    metadata = self.transport.request(
                        "GET", f"{self.api}/issue/createmeta",
                        params={"projectKeys": project_key, "issuetypeIds": issue_type_id, "expand": "projects.issuetypes.fields"},
                    )
                    projects = metadata.get("projects", [])
                    issue_types = projects[0].get("issuetypes", []) if projects else []
                    field_map = issue_types[0].get("fields", {}) if issue_types else {}
                    required = {key: bool(value.get("required")) for key, value in field_map.items()}
            except AtlassianError:
                # Global field metadata is still useful; validation reports that
                # create metadata could not be resolved for this scope.
                pass
        normalized = []
        for item in fields:
            field_id = item.get("id", "")
            schema = item.get("schema") or {}
            normalized.append({
                "id": field_id,
                "name": item.get("name", field_id),
                "custom": bool(item.get("custom")),
                "orderable": bool(item.get("orderable", True)),
                "navigable": bool(item.get("navigable", True)),
                "searchable": bool(item.get("searchable", True)),
                "required": required.get(field_id, False),
                "read_only": not bool(item.get("orderable", True)),
                "type": jira_field_type(schema),
                "schema": schema,
            })
        return normalized

    def issue_types(self, project_key: str) -> list[dict]:
        project = self.transport.request("GET", f"{self.api}/project/{project_key}")
        return project.get("issueTypes", [])

    def search(self, jql: str, max_results: int = 50, fields: list[str] | None = None) -> dict:
        fields = fields or [
            "summary", "description", "status", "assignee", "reporter", "priority",
            "labels", "components", "project", "issuetype", "comment", "issuelinks", "subtasks", "updated",
        ]
        body = {"jql": jql, "maxResults": min(max_results, 500), "fields": fields}
        path = f"{self.api}/search/jql" if self.cloud else f"{self.api}/search"
        return self.transport.request("POST", path, json=body)

    def get_issue(self, key: str) -> dict:
        return self.transport.request("GET", f"{self.api}/issue/{key}", params={"expand": "names,schema,renderedFields"})

    def get_comments(self, key: str, limit: int = 50) -> list[dict]:
        data = self.transport.request("GET", f"{self.api}/issue/{key}/comment", params={"maxResults": min(limit, 100)})
        return data.get("comments", [])

    def issue_context(self, key: str) -> dict:
        issue = self.get_issue(key)
        fields = issue.get("fields", {})
        comments = fields.get("comment", {}).get("comments") if isinstance(fields.get("comment"), dict) else None
        if comments is None:
            comments = self.get_comments(key, 20)
        return {
            "key": issue.get("key", key),
            "summary": fields.get("summary", ""),
            "description": adf_to_text(fields.get("description")),
            "issue_type": (fields.get("issuetype") or {}).get("name", ""),
            "status": (fields.get("status") or {}).get("name", ""),
            "priority": (fields.get("priority") or {}).get("name", ""),
            "labels": fields.get("labels") or [],
            "components": [item.get("name", "") for item in fields.get("components") or []],
            "assignee": (fields.get("assignee") or {}).get("displayName", ""),
            "reporter": (fields.get("reporter") or {}).get("displayName", ""),
            "comments": [adf_to_text(item.get("body")) for item in comments[-20:]],
            "linked_issues": [item.get("outwardIssue", item.get("inwardIssue", {})).get("key") for item in fields.get("issuelinks") or []],
            "subtasks": [item.get("key") for item in fields.get("subtasks") or []],
            "fields": fields,
        }

    def permissions(self, issue_key: str = "", project_key: str = "") -> dict:
        params: dict[str, str] = {"permissions": "BROWSE_PROJECTS,ADD_COMMENTS,CREATE_ISSUES,EDIT_ISSUES"}
        if issue_key:
            params["issueKey"] = issue_key
        elif project_key:
            params["projectKey"] = project_key
        return self.transport.request("GET", f"{self.api}/mypermissions", params=params).get("permissions", {})

    def capability_preflight(self, issue_key: str = "", project_key: str = "") -> dict:
        capabilities: dict[str, dict] = {}

        def check(name: str, fn) -> None:
            try:
                value = fn()
                capabilities[name] = {"allowed": True, "detail": value}
            except AtlassianError as error:
                capabilities[name] = {"allowed": False, "error": error.as_dict()}

        check("can_authenticate", self.myself)
        check("can_read_fields", lambda: {"count": len(self.list_fields())})
        check("can_browse_projects", lambda: {"count": len(self.list_projects(5))})
        if issue_key:
            check("can_read_issues", lambda: {"key": self.get_issue(issue_key).get("key")})
        else:
            check("can_search_issues", lambda: {"count": len(self.search("ORDER BY updated DESC", 1).get("issues", []))})
        try:
            permissions = self.permissions(issue_key, project_key)
            for capability, jira_permission in {
                "can_browse_projects": "BROWSE_PROJECTS",
                "can_add_comments": "ADD_COMMENTS",
                "can_create_issues": "CREATE_ISSUES",
                "can_edit_issues": "EDIT_ISSUES",
            }.items():
                allowed = bool((permissions.get(jira_permission) or {}).get("havePermission"))
                capabilities[capability] = {"allowed": allowed, "permission": jira_permission}
        except AtlassianError as error:
            capabilities["can_add_comments"] = {"allowed": False, "error": error.as_dict()}
        return capabilities

    def add_comment(self, key: str, text: str, correlation_id: str) -> dict:
        if self.cloud:
            body = {
                "body": adf_document(text),
                "properties": [{"key": "soc-workbench.audit", "value": {"correlation_id": correlation_id}}],
            }
        else:
            body = {"body": text}
        return self.transport.request("POST", f"{self.api}/issue/{key}/comment", json=body)

    def comment_hashes(self, key: str, limit: int = 50) -> set[str]:
        return {
            hashlib.sha256(adf_to_text(item.get("body")).strip().encode("utf-8")).hexdigest()
            for item in self.get_comments(key, limit)
        }


def issue_context_json(context: dict) -> str:
    """Stable, bounded prompt context; issue content remains untrusted data."""
    bounded = dict(context)
    bounded["comments"] = (bounded.get("comments") or [])[-10:]
    bounded.pop("fields", None)
    return json.dumps(bounded, ensure_ascii=False, default=str)[:30000]

