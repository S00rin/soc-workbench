"""Backend enforcement for module RBAC, feature expiry and action history."""
from __future__ import annotations

import time
import uuid

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..database import SessionLocal
from ..models.governance import UserActivity
from ..security import AuthContext, resolve_token_context
from .access_control import feature_state, module_allowed, module_feature_key

PATH_MODULES = [
    (("/api/dashboard",), "dashboard"),
    (("/api/documents", "/api/inputs", "/api/knowledge", "/api/iocs", "/api/projects", "/api/search"), "data"),
    (("/api/atlassian", "/api/jira", "/api/splunk", "/api/integrations", "/api/wikijs"), "integrations"),
    (("/api/intel", "/api/automation"), "intelligence"),
    (("/api/reports",), "reports"),
    (("/api/jobs", "/api/notifications", "/api/backup"), "operations"),
    (("/api/prompts", "/api/llm"), "prompts"),
    (("/api/settings",), "settings"),
]


def module_for_path(path: str) -> str:
    for prefixes, module in PATH_MODULES:
        if path.startswith(prefixes):
            return module
    return "general"


def specific_features(path: str) -> list[str]:
    features: list[str] = []
    if "/jira" in path:
        features.append("integration.jira")
    if "/confluence" in path:
        features.append("integration.confluence")
    if "/wikijs" in path:
        features.append("integration.wikijs")
    if "/splunk" in path:
        features.append("integration.splunk")
    if "/chat" in path:
        features.append("integration.chat")
    if "/bulk" in path:
        features.append("integration.bulk")
    if path.endswith("/analyze") or "/comments/preview" in path:
        features.append("ai.processing")
    return features


class ProductAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/") or path in {"/api/health", "/api/auth/login"}:
            return await call_next(request)

        trace_id = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex
        module = module_for_path(path)
        context: AuthContext | None = None
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            db = SessionLocal()
            try:
                context = resolve_token_context(auth.split(" ", 1)[1], db)
                if context.must_change_password and path not in {
                    "/api/auth/me", "/api/access/effective", "/api/auth/change-password",
                }:
                    return JSONResponse(403, {"detail": {
                        "code": "password_change_required",
                        "message": "Change the temporary password before using the workspace.",
                    }}, headers={"X-Correlation-ID": trace_id})
                if module != "general" and not module_allowed(context.role, list(context.module_permissions), module):
                    return JSONResponse(403, {"detail": {"code": "module_forbidden", "module": module, "message": "Your account cannot access this module."}}, headers={"X-Correlation-ID": trace_id})
                if module != "general" and not path.startswith("/api/admin"):
                    state = feature_state(db, context.tenant_id, module_feature_key(module), context.role)
                    if not state["active"]:
                        return JSONResponse(403, {"detail": {"code": "feature_unavailable", "feature": module_feature_key(module), "status": state["status"], "expires_at": str(state.get("expires_at") or "")}}, headers={"X-Correlation-ID": trace_id})
                    for key in specific_features(path):
                        state = feature_state(db, context.tenant_id, key, context.role)
                        if not state["active"]:
                            return JSONResponse(403, {"detail": {"code": "feature_unavailable", "feature": key, "status": state["status"], "expires_at": str(state.get("expires_at") or "")}}, headers={"X-Correlation-ID": trace_id})
            except HTTPException as error:
                return JSONResponse(error.status_code, {"detail": error.detail}, headers={"X-Correlation-ID": trace_id})
            finally:
                db.close()

        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = trace_id
        if context and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            db = SessionLocal()
            try:
                db.add(UserActivity(
                    tenant_id=context.tenant_id,
                    actor_user_id=context.username,
                    module_key=module,
                    action=f"{request.method.lower()}:{path}",
                    method=request.method,
                    path=path[:500],
                    status_code=response.status_code,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    correlation_id=trace_id,
                    details={},
                ))
                db.commit()
            finally:
                db.close()
        return response
