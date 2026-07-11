"""Application settings + sensitive patterns (Module 15)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.core import SensitivePattern
from ..security import get_current_user
from ..services import settings_service as svc

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingUpdate(BaseModel):
    key: str
    value: str
    category: str = "general"


class BulkUpdate(BaseModel):
    items: list[SettingUpdate]


@router.get("")
def list_settings(db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    return svc.get_all_safe(db)


@router.put("")
def update_settings(payload: BulkUpdate, db: Session = Depends(get_db),
                    user: str = Depends(get_current_user)):
    for item in payload.items:
        svc.set_value(db, item.key, item.value, item.category)
    return {"ok": True, "updated": len(payload.items)}


# --- Sensitive patterns (Module 3) ---
class PatternIn(BaseModel):
    label: str
    pattern: str
    is_regex: bool = True
    enabled: bool = True
    token_prefix: str = "CUSTOM"


@router.get("/patterns")
def list_patterns(db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    rows = db.query(SensitivePattern).all()
    return [{c.name: getattr(r, c.name) for c in SensitivePattern.__table__.columns}
            for r in rows]


@router.post("/patterns")
def create_pattern(p: PatternIn, db: Session = Depends(get_db),
                   user: str = Depends(get_current_user)):
    row = SensitivePattern(**p.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.delete("/patterns/{pattern_id}")
def delete_pattern(pattern_id: int, db: Session = Depends(get_db),
                   user: str = Depends(get_current_user)):
    row = db.get(SensitivePattern, pattern_id)
    if not row:
        raise HTTPException(404, "Pattern not found")
    db.delete(row)
    db.commit()
    return {"ok": True}
