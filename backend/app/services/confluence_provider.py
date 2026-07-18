"""Confluence Cloud/Data Center provider."""
from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from .atlassian_http import AtlassianError, AtlassianTransport


def storage_to_text(value: Any) -> str:
    if isinstance(value, str):
        return BeautifulSoup(value, "html.parser").get_text("\n", strip=True)
    if isinstance(value, dict):
        return storage_to_text(value.get("value") or value.get("storage") or "")
    return ""


class ConfluenceProvider:
    def __init__(self, transport: AtlassianTransport, cloud: bool):
        self.transport = transport
        self.cloud = cloud

    def current_user(self) -> dict:
        path = "/wiki/rest/api/user/current" if self.cloud else "/rest/api/user/current"
        return self.transport.request("GET", path)

    def list_spaces(self, limit: int = 50) -> list[dict]:
        if self.cloud:
            return self.transport.request("GET", "/wiki/api/v2/spaces", params={"limit": min(limit, 100)}).get("results", [])
        return self.transport.request("GET", "/rest/api/space", params={"limit": min(limit, 100)}).get("results", [])

    def search(self, cql: str, limit: int = 50) -> dict:
        path = "/wiki/rest/api/search" if self.cloud else "/rest/api/search"
        return self.transport.request("GET", path, params={"cql": cql, "limit": min(limit, 100)})

    def get_page(self, page_id: str) -> dict:
        if self.cloud:
            return self.transport.request(
                "GET", f"/wiki/api/v2/pages/{page_id}",
                params={"body-format": "storage", "include-labels": "true"},
            )
        return self.transport.request(
            "GET", f"/rest/api/content/{page_id}",
            params={"expand": "body.storage,version,ancestors,metadata.labels,space"},
        )

    def page_context(self, page_id: str) -> dict:
        page = self.get_page(page_id)
        body = page.get("body", {})
        storage = body.get("storage", body)
        return {
            "id": page.get("id", page_id),
            "title": page.get("title", ""),
            "status": page.get("status", ""),
            "space_id": page.get("spaceId") or (page.get("space") or {}).get("key", ""),
            "author_id": page.get("authorId", ""),
            "owner_id": page.get("ownerId", ""),
            "parent_id": page.get("parentId") or ((page.get("ancestors") or [{}])[-1].get("id", "") if page.get("ancestors") else ""),
            "version": (page.get("version") or {}).get("number", 0),
            "labels": [item.get("name", "") for item in (page.get("labels") or page.get("metadata", {}).get("labels", {}).get("results", []))],
            "content": storage_to_text(storage),
            "comments": [storage_to_text(item.get("body", {})) for item in self.get_footer_comments(page_id, 20)],
        }

    def get_footer_comments(self, page_id: str, limit: int = 50) -> list[dict]:
        if self.cloud:
            data = self.transport.request(
                "GET", "/wiki/api/v2/footer-comments",
                params={"page-id": page_id, "limit": min(limit, 100), "body-format": "storage"},
            )
        else:
            data = self.transport.request(
                "GET", f"/rest/api/content/{page_id}/child/comment",
                params={"limit": min(limit, 100), "expand": "body.storage"},
            )
        return data.get("results", [])

    def capability_preflight(self, page_id: str = "") -> dict:
        capabilities: dict[str, dict] = {}

        def check(name: str, fn) -> None:
            try:
                value = fn()
                capabilities[name] = {"allowed": True, "detail": value}
            except AtlassianError as error:
                capabilities[name] = {"allowed": False, "error": error.as_dict()}

        check("can_authenticate", self.current_user)
        check("can_read_spaces", lambda: {"count": len(self.list_spaces(5))})
        check("can_search_pages", lambda: {"count": len(self.search('type=page', 1).get("results", []))})
        if page_id:
            check("can_read_pages", lambda: {"id": self.get_page(page_id).get("id")})
            # There is no side-effect-free universal "can comment" endpoint.
            # Report it as indeterminate until a real post is attempted.
            capabilities["can_add_comments"] = {
                "allowed": None,
                "detail": "Confluence has no side-effect-free comment permission probe; preview is allowed and post errors are classified.",
            }
        return capabilities

    def add_footer_comment(self, page_id: str, text: str) -> dict:
        if self.cloud:
            return self.transport.request(
                "POST", "/wiki/api/v2/footer-comments",
                json={"pageId": page_id, "body": {"representation": "storage", "value": f"<p>{_escape(text)}</p>"}},
            )
        return self.transport.request(
            "POST", "/rest/api/content",
            json={
                "type": "comment",
                "container": {"id": page_id, "type": "page"},
                "body": {"storage": {"value": f"<p>{_escape(text)}</p>", "representation": "storage"}},
            },
        )


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
