"""Settings + sensitive-pattern management (Module 15 / Module 3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.core import SensitivePattern
from ..schemas import (
    PatternIn,
    PatternOut,
    SettingOut,
    SettingsUpdate,
)
from ..security import get_current_user
from ..services import settings_service as svc

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=list[SettingOut])
def list_settings(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    return svc.get_all_safe(db)


@router.put("", response_model=list[SettingOut])
def update_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    for key, value in payload.values.items():
        # Preserve the existing category if the key is known.
        existing = svc.DEFAULTS.get(key)
        category = existing[1] if existing else "general"
        svc.set_value(db, key, value, category=category)
    return svc.get_all_safe(db)


# --- Sensitive patterns ---------------------------------------------------
@router.get("/patterns", response_model=list[PatternOut])
def list_patterns(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    return db.query(SensitivePattern).order_by(SensitivePattern.label).all()


@router.post("/patterns", response_model=PatternOut)
def create_pattern(
    payload: PatternIn,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    row = SensitivePattern(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/patterns/{pattern_id}", response_model=PatternOut)
def update_pattern(
    pattern_id: int,
    payload: PatternIn,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    row = db.get(SensitivePattern, pattern_id)
    if not row:
        raise HTTPException(404, "Pattern not found")
    for k, v in payload.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/patterns/{pattern_id}")
def delete_pattern(
    pattern_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    row = db.get(SensitivePattern, pattern_id)
    if not row:
        raise HTTPException(404, "Pattern not found")
    db.delete(row)
    db.commit()
    return {"ok": True}
