"""Administration APIs for users, module RBAC, feature expiry and activity history."""
from __future__ import annotations

from datetime import datetime, timezone
import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.governance import FeaturePolicy, UserAccount, UserActivity
from ..security import AuthContext, get_auth_context, require_admin
from ..services.access_control import (
    ALL_MODULE_KEYS, FEATURE_CATALOG, MODULE_CATALOG, feature_state, hash_password,
    safe_user, verify_password,
)
from ..services.integration_history import audit

router = APIRouter(tags=["access-control"])


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=120, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(default="", max_length=180)
    email: str = Field(default="", max_length=240)
    password: str = Field(min_length=12, max_length=256)
    role: Literal["admin", "analyst", "viewer"] = "analyst"
    module_permissions: list[str] = Field(default_factory=lambda: ["dashboard"])
    active: bool = True
    must_change_password: bool = True

    @field_validator("module_permissions")
    @classmethod
    def valid_modules(cls, value: list[str]) -> list[str]:
        invalid = set(value) - set(ALL_MODULE_KEYS)
        if invalid:
            raise ValueError(f"Unknown modules: {', '.join(sorted(invalid))}")
        return sorted(set(value))


class UserUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=180)
    email: str | None = Field(default=None, max_length=240)
    role: Literal["admin", "analyst", "viewer"] | None = None
    module_permissions: list[str] | None = None
    active: bool | None = None
    must_change_password: bool | None = None

    @field_validator("module_permissions")
    @classmethod
    def valid_modules(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        invalid = set(value) - set(ALL_MODULE_KEYS)
        if invalid:
            raise ValueError(f"Unknown modules: {', '.join(sorted(invalid))}")
        return sorted(set(value))


class PasswordResetIn(BaseModel):
    password: str = Field(min_length=12, max_length=256)
    must_change_password: bool = True


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class FeaturePolicyIn(BaseModel):
    enabled: bool = True
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    allowed_roles: list[Literal["admin", "analyst", "viewer"]] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)

    @field_validator("expires_at")
    @classmethod
    def expiry_is_reasonable(cls, value: datetime | None) -> datetime | None:
        if value and value.year > datetime.now(timezone.utc).year + 20:
            raise ValueError("Expiry cannot be more than 20 years in the future")
        return value


@router.get("/api/access/effective")
def effective_access(db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    modules = ALL_MODULE_KEYS if context.role == "admin" else list(context.module_permissions)
    features = {
        item["key"]: feature_state(db, context.tenant_id, item["key"], context.role)
        for item in FEATURE_CATALOG
    }
    return {
        "user": {
            "id": context.user_id, "username": context.username, "display_name": context.display_name,
            "tenant_id": context.tenant_id, "role": context.role,
        },
        "modules": modules,
        "features": features,
        "module_catalog": MODULE_CATALOG,
    }


@router.get("/api/admin/users")
def list_users(db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    rows = db.query(UserAccount).filter(UserAccount.tenant_id == context.tenant_id).order_by(UserAccount.username).all()
    return [safe_user(row) for row in rows]


@router.post("/api/admin/users")
def create_user(payload: UserCreateIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    row = UserAccount(
        tenant_id=context.tenant_id,
        username=payload.username.strip(),
        display_name=payload.display_name.strip(),
        email=payload.email.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        module_permissions=ALL_MODULE_KEYS if payload.role == "admin" else payload.module_permissions,
        active=payload.active,
        must_change_password=payload.must_change_password,
        password_changed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, {"code": "username_exists", "message": "Username already exists in this tenant."}) from error
    db.refresh(row)
    audit(db, context, "user.create", "user", str(row.id), details={"username": row.username, "role": row.role})
    return safe_user(row)


@router.put("/api/admin/users/{user_id}")
def update_user(user_id: int, payload: UserUpdateIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    row = db.query(UserAccount).filter(UserAccount.id == user_id, UserAccount.tenant_id == context.tenant_id).first()
    if row is None:
        raise HTTPException(404, "User not found")
    changes = payload.model_dump(exclude_unset=True)
    if row.id == context.user_id and changes.get("active") is False:
        raise HTTPException(409, "You cannot deactivate your own account")
    for key, value in changes.items():
        setattr(row, key, value)
    if row.role == "admin":
        row.module_permissions = ALL_MODULE_KEYS
    db.commit()
    audit(db, context, "user.update", "user", str(row.id), details={"fields": sorted(changes)})
    return safe_user(row)


@router.delete("/api/admin/users/{user_id}")
def deactivate_user(user_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    if user_id == context.user_id:
        raise HTTPException(409, "You cannot deactivate your own account")
    row = db.query(UserAccount).filter(UserAccount.id == user_id, UserAccount.tenant_id == context.tenant_id).first()
    if row is None:
        raise HTTPException(404, "User not found")
    row.active = False
    db.commit()
    audit(db, context, "user.deactivate", "user", str(row.id), details={"username": row.username})
    return {"ok": True}


@router.post("/api/admin/users/{user_id}/reset-password")
def reset_password(user_id: int, payload: PasswordResetIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    row = db.query(UserAccount).filter(UserAccount.id == user_id, UserAccount.tenant_id == context.tenant_id).first()
    if row is None:
        raise HTTPException(404, "User not found")
    row.password_hash = hash_password(payload.password)
    row.must_change_password = payload.must_change_password
    row.password_changed_at = datetime.now(timezone.utc)
    db.commit()
    audit(db, context, "user.password_reset", "user", str(row.id), details={"username": row.username})
    return {"ok": True}


@router.post("/api/auth/change-password")
def change_password(payload: PasswordChangeIn, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    row = db.query(UserAccount).filter(
        UserAccount.id == context.user_id,
        UserAccount.tenant_id == context.tenant_id,
    ).first()
    if row is None or not verify_password(payload.current_password, row.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    row.password_hash = hash_password(payload.new_password)
    row.must_change_password = False
    row.password_changed_at = datetime.now(timezone.utc)
    db.commit()
    audit(db, context, "user.password_change", "user", str(row.id))
    return {"ok": True}


@router.get("/api/admin/features")
def list_features(db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    rows = {row.feature_key: row for row in db.query(FeaturePolicy).filter(FeaturePolicy.tenant_id == context.tenant_id).all()}
    return [
        {**item, "policy_id": rows.get(item["key"]).id if rows.get(item["key"]) else None,
         **feature_state(db, context.tenant_id, item["key"], context.role)}
        for item in FEATURE_CATALOG
    ]


@router.put("/api/admin/features/{feature_key}")
def update_feature(feature_key: str, payload: FeaturePolicyIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    if feature_key not in {item["key"] for item in FEATURE_CATALOG}:
        raise HTTPException(404, "Unknown feature")
    if payload.starts_at and payload.expires_at and payload.expires_at <= payload.starts_at:
        raise HTTPException(422, "expires_at must be after starts_at")
    row = db.query(FeaturePolicy).filter(FeaturePolicy.tenant_id == context.tenant_id, FeaturePolicy.feature_key == feature_key).first()
    if row is None:
        row = FeaturePolicy(tenant_id=context.tenant_id, feature_key=feature_key)
        db.add(row)
    row.enabled = payload.enabled
    row.starts_at = payload.starts_at
    row.expires_at = payload.expires_at
    row.allowed_roles = payload.allowed_roles
    row.policy_config = payload.config
    row.updated_by = context.username
    db.commit()
    audit(db, context, "feature_policy.update", "feature", feature_key, details={"enabled": payload.enabled, "expires_at": str(payload.expires_at or "")})
    return {"key": feature_key, **feature_state(db, context.tenant_id, feature_key, context.role)}


@router.get("/api/admin/activity")
def activity_history(
    actor: str = "", module: str = "", action: str = "", status: str = "", status_code: int | None = None,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db), context: AuthContext = Depends(require_admin),
):
    query = db.query(UserActivity).filter(UserActivity.tenant_id == context.tenant_id)
    if actor:
        query = query.filter(UserActivity.actor_user_id == actor[:120])
    if module:
        query = query.filter(UserActivity.module_key == module[:80])
    if action:
        query = query.filter(UserActivity.action.contains(action[:120]))
    if status_code is not None:
        query = query.filter(UserActivity.status_code == status_code)
    elif status == "success":
        query = query.filter(UserActivity.status_code < 400)
    elif status == "failed":
        query = query.filter(UserActivity.status_code >= 400)
    total = query.count()
    rows = query.order_by(desc(UserActivity.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [{column.name: getattr(row, column.name) for column in row.__table__.columns} for row in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/api/admin/activity-export.csv")
def export_activity(
    actor: str = "", module: str = "", action: str = "", status: str = "",
    db: Session = Depends(get_db), context: AuthContext = Depends(require_admin),
):
    query = db.query(UserActivity).filter(UserActivity.tenant_id == context.tenant_id)
    if actor:
        query = query.filter(UserActivity.actor_user_id == actor[:120])
    if module:
        query = query.filter(UserActivity.module_key == module[:80])
    if action:
        query = query.filter(UserActivity.action.contains(action[:120]))
    if status == "success":
        query = query.filter(UserActivity.status_code < 400)
    elif status == "failed":
        query = query.filter(UserActivity.status_code >= 400)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["time", "user", "module", "action", "method", "path", "status_code", "duration_ms", "trace_id"])
    for row in query.order_by(desc(UserActivity.created_at)).limit(10000):
        writer.writerow([row.created_at.isoformat(), row.actor_user_id, row.module_key, row.action, row.method, row.path, row.status_code, row.duration_ms, row.correlation_id])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=audit-log.csv"})
