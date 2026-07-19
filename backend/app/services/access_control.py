"""Central user, module permission and time-bounded feature policy service."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.governance import FeaturePolicy, UserAccount

MODULE_CATALOG = [
    {"key": "dashboard", "label": "Dashboard", "description": "Operational overview and quick actions"},
    {"key": "data", "label": "Data & IoCs", "description": "Processing, knowledge, IoCs and projects"},
    {"key": "integrations", "label": "Integrations", "description": "Jira, Confluence, Wiki.js and Splunk"},
    {"key": "intelligence", "label": "Intelligence", "description": "Internet intelligence and automation"},
    {"key": "reports", "label": "Reports", "description": "Report creation and export"},
    {"key": "operations", "label": "Operations", "description": "Jobs, notifications and backups"},
    {"key": "prompts", "label": "Prompt Library", "description": "Reusable prompts and LLM operations"},
    {"key": "settings", "label": "Settings", "description": "Application settings"},
]

FEATURE_CATALOG = [
    {"key": "module.dashboard", "label": "Dashboard", "module": "dashboard"},
    {"key": "module.data", "label": "Data & IoCs", "module": "data"},
    {"key": "module.integrations", "label": "Integration Hub", "module": "integrations"},
    {"key": "integration.jira", "label": "Jira", "module": "integrations"},
    {"key": "integration.confluence", "label": "Confluence", "module": "integrations"},
    {"key": "integration.wikijs", "label": "Wiki.js", "module": "integrations"},
    {"key": "integration.splunk", "label": "Splunk", "module": "integrations"},
    {"key": "integration.chat", "label": "Integration Prompt Chat", "module": "integrations"},
    {"key": "integration.bulk", "label": "Bulk Operations", "module": "integrations"},
    {"key": "module.intelligence", "label": "Intelligence & Automation", "module": "intelligence"},
    {"key": "module.reports", "label": "Reports", "module": "reports"},
    {"key": "module.operations", "label": "Jobs & Notifications", "module": "operations"},
    {"key": "module.prompts", "label": "Prompt Library", "module": "prompts"},
    {"key": "module.settings", "label": "Settings", "module": "settings"},
    {"key": "ai.processing", "label": "AI Processing", "module": "data"},
]

ALL_MODULE_KEYS = [item["key"] for item in MODULE_CATALOG]


def hash_password(password: str, *, enforce_policy: bool = True) -> str:
    if not password:
        raise ValueError("Password cannot be empty")
    if enforce_policy and len(password) < 12:
        raise ValueError("Password must be at least 12 characters")
    salt = os.urandom(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(derived).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_raw, expected_raw = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_raw)
        expected = base64.urlsafe_b64decode(expected_raw)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def seed_access_defaults(db: Session) -> None:
    settings = get_settings()
    admin = db.query(UserAccount).filter(
        UserAccount.tenant_id == settings.default_tenant_id,
        UserAccount.username == settings.admin_username,
    ).first()
    if admin is None:
        admin = UserAccount(
            tenant_id=settings.default_tenant_id,
            username=settings.admin_username,
            display_name="Administrator",
            # Preserve the existing bootstrap credential during a non-breaking
            # upgrade, even when an old local deployment used a short password.
            # New/reset passwords are still required to satisfy the 12-char API policy.
            password_hash=hash_password(settings.admin_password, enforce_policy=False),
            role="admin",
            module_permissions=ALL_MODULE_KEYS,
            active=True,
            must_change_password=False,
            password_changed_at=datetime.now(timezone.utc),
        )
        db.add(admin)
    for item in FEATURE_CATALOG:
        exists = db.query(FeaturePolicy).filter(
            FeaturePolicy.tenant_id == settings.default_tenant_id,
            FeaturePolicy.feature_key == item["key"],
        ).first()
        if exists is None:
            db.add(FeaturePolicy(
                tenant_id=settings.default_tenant_id,
                feature_key=item["key"],
                enabled=True,
                allowed_roles=[],
                policy_config={},
                updated_by=settings.admin_username,
            ))
    db.commit()


def authenticate(db: Session, username: str, password: str) -> UserAccount | None:
    settings = get_settings()
    row = db.query(UserAccount).filter(
        UserAccount.tenant_id == settings.default_tenant_id,
        UserAccount.username == username.strip(),
        UserAccount.active.is_(True),
    ).first()
    if row is None or not verify_password(password, row.password_hash):
        return None
    row.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return row


def safe_user(row: UserAccount) -> dict:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "username": row.username,
        "display_name": row.display_name,
        "email": row.email,
        "role": row.role,
        "module_permissions": row.module_permissions or [],
        "active": row.active,
        "must_change_password": row.must_change_password,
        "last_login_at": row.last_login_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def policy_state(row: FeaturePolicy | None, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if row is None:
        return {"enabled": True, "active": True, "status": "active", "starts_at": None, "expires_at": None, "allowed_roles": []}
    starts = _aware(row.starts_at)
    expires = _aware(row.expires_at)
    if not row.enabled:
        status_value = "disabled"
    elif starts and starts > now:
        status_value = "scheduled"
    elif expires and expires <= now:
        status_value = "expired"
    else:
        status_value = "active"
    return {
        "enabled": row.enabled,
        "active": status_value == "active",
        "status": status_value,
        "starts_at": row.starts_at,
        "expires_at": row.expires_at,
        "allowed_roles": row.allowed_roles or [],
        "config": row.policy_config or {},
    }


def feature_state(db: Session, tenant_id: str, feature_key: str, role: str = "") -> dict:
    row = db.query(FeaturePolicy).filter(
        FeaturePolicy.tenant_id == tenant_id,
        FeaturePolicy.feature_key == feature_key,
    ).first()
    state = policy_state(row)
    roles = state.get("allowed_roles") or []
    if state["active"] and roles and role not in roles:
        state = {**state, "active": False, "status": "role_restricted"}
    return state


def require_feature(db: Session, tenant_id: str, role: str, feature_key: str) -> None:
    state = feature_state(db, tenant_id, feature_key, role)
    if not state["active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "feature_unavailable", "feature": feature_key, "status": state["status"], "expires_at": state.get("expires_at")},
        )


def module_allowed(role: str, permissions: list[str], module_key: str) -> bool:
    return role == "admin" or module_key in (permissions or [])


def module_feature_key(module_key: str) -> str:
    return f"module.{module_key}"
