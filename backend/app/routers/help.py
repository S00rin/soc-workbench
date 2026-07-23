"""Multi-language (English/Farsi) user and admin help guides (Module 16)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.help import HelpGuide
from ..security import AuthContext, get_auth_context, require_admin

router = APIRouter(prefix="/api/help", tags=["help"])


class GuideIn(BaseModel):
    slug: str = Field(min_length=1, max_length=160)
    language: str = Field(default="en", pattern="^(en|fa)$")
    audience: str = Field(default="user", pattern="^(user|admin)$")
    category: str = Field(default="General", max_length=120)
    title: str = Field(min_length=1, max_length=240)
    summary: str = Field(default="", max_length=400)
    content: str = ""
    order_index: int = 0


def _visible(row: HelpGuide, role: str) -> bool:
    return row.audience != "admin" or role == "admin"


def _out(row: HelpGuide) -> dict:
    return {
        "id": row.id, "slug": row.slug, "language": row.language, "audience": row.audience,
        "category": row.category, "title": row.title, "summary": row.summary,
        "content": row.content, "order_index": row.order_index, "is_builtin": row.is_builtin,
        "updated_by": row.updated_by, "created_at": row.created_at, "updated_at": row.updated_at,
    }


@router.get("/guides")
def list_guides(
    language: str = "", audience: str = "", category: str = "",
    db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context),
):
    query = db.query(HelpGuide)
    if language:
        query = query.filter(HelpGuide.language == language)
    if category:
        query = query.filter(HelpGuide.category == category)
    if audience:
        query = query.filter(HelpGuide.audience == audience)
    rows = query.order_by(HelpGuide.audience, HelpGuide.category, HelpGuide.order_index, HelpGuide.title).all()
    return [_out(r) for r in rows if _visible(r, context.role)]


@router.get("/guides/{guide_id}")
def get_guide(guide_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    row = db.get(HelpGuide, guide_id)
    if not row or not _visible(row, context.role):
        raise HTTPException(404, "Guide not found")
    return _out(row)


@router.post("/guides")
def create_guide(payload: GuideIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    row = HelpGuide(**payload.model_dump(), is_builtin=False, updated_by=context.username)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.put("/guides/{guide_id}")
def update_guide(guide_id: int, payload: GuideIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    row = db.get(HelpGuide, guide_id)
    if not row:
        raise HTTPException(404, "Guide not found")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.updated_by = context.username
    db.commit()
    db.refresh(row)
    return _out(row)


@router.delete("/guides/{guide_id}")
def delete_guide(guide_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    row = db.get(HelpGuide, guide_id)
    if not row:
        raise HTTPException(404, "Guide not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/categories")
def list_categories(db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    rows = db.query(HelpGuide).order_by(HelpGuide.category).all()
    seen = []
    for r in rows:
        if _visible(r, context.role) and r.category not in seen:
            seen.append(r.category)
    return seen
