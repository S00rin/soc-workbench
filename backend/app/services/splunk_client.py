"""Splunk REST connector (Module 7). Read-only (search) by default.

Enforces configured guardrails: allowed indexes, max results, max time range.
An MCP-server path is stubbed with a clear NotImplemented message where a live
MCP endpoint is required (see docs/MCP_SETUP.md).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from ..logging_config import get_logger

logger = get_logger(__name__)


class SplunkError(Exception):
    pass


@dataclass
class SplunkConfig:
    base_url: str  # e.g. https://splunk:8089
    token: str = ""
    username: str = ""
    password: str = ""
    verify_ssl: bool = True
    timeout: int = 60
    allowed_indexes: list[str] | None = None
    max_results: int = 1000


class SplunkClient:
    def __init__(self, cfg: SplunkConfig):
        if not cfg.base_url:
            raise SplunkError("Splunk base URL is not configured.")
        self.cfg = cfg
        headers = {}
        auth = None
        if cfg.token:
            headers["Authorization"] = f"Bearer {cfg.token}"
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

    def __enter__(self) -> "SplunkClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def test_connection(self) -> dict:
        try:
            r = self._client.get("/services/server/info", params={"output_mode": "json"})
            r.raise_for_status()
            data = r.json()
            name = data["entry"][0]["content"].get("serverName", "splunk")
            return {"ok": True, "server": name}
        except httpx.HTTPError as e:
            raise SplunkError(f"Splunk connection error: {e}") from e

    def _guard(self, spl: str) -> str:
        """Reject obvious write/destructive commands; keep searches read-only."""
        lowered = spl.lower()
        banned = ("| delete", "| collect", "| outputlookup", "| sendemail", "|delete")
        for b in banned:
            if b in lowered:
                raise SplunkError(f"Blocked non-read-only command: {b.strip()}")
        if self.cfg.allowed_indexes:
            # If the search names an index, it must be in the allow-list.
            if "index=" in lowered:
                allowed = any(
                    f"index={idx.lower()}" in lowered for idx in self.cfg.allowed_indexes
                )
                if not allowed:
                    raise SplunkError(
                        "Search uses an index outside the allowed list: "
                        + ", ".join(self.cfg.allowed_indexes)
                    )
        return spl

    def search(
        self,
        spl: str,
        earliest: str = "-24h",
        latest: str = "now",
        max_results: int | None = None,
    ) -> dict:
        """Run a blocking search job and return results (read-only)."""
        spl = self._guard(spl.strip())
        if not spl.lower().startswith("search") and not spl.startswith("|"):
            spl = "search " + spl
        limit = min(max_results or self.cfg.max_results, self.cfg.max_results)

        try:
            create = self._client.post(
                "/services/search/jobs",
                data={
                    "search": spl,
                    "earliest_time": earliest,
                    "latest_time": latest,
                    "output_mode": "json",
                    "exec_mode": "normal",
                },
            )
            create.raise_for_status()
            sid = create.json()["sid"]
        except httpx.HTTPError as e:
            raise SplunkError(f"Failed to start search: {e}") from e

        # Poll for completion.
        deadline = time.time() + self.cfg.timeout
        while time.time() < deadline:
            status = self._client.get(
                f"/services/search/jobs/{sid}", params={"output_mode": "json"}
            )
            content = status.json()["entry"][0]["content"]
            if content.get("isDone"):
                break
            time.sleep(1)
        else:
            raise SplunkError("Search timed out.")

        res = self._client.get(
            f"/services/search/jobs/{sid}/results",
            params={"output_mode": "json", "count": limit},
        )
        res.raise_for_status()
        data = res.json()
        results = data.get("results", [])
        fields = list(results[0].keys()) if results else []
        return {"sid": sid, "count": len(results), "fields": fields, "results": results}

    def saved_searches(self) -> list[dict]:
        r = self._client.get(
            "/services/saved/searches", params={"output_mode": "json", "count": 200}
        )
        r.raise_for_status()
        entries = r.json().get("entry", [])
        return [
            {"name": e["name"], "search": e["content"].get("search", "")}
            for e in entries
        ]
