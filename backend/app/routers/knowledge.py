"""SOC knowledge base (Module 8)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.content import KnowledgeItem
from ..security import get_current_user

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

ITEM_TYPES = [
    "article", "note", "runbook", "playbook", "troubleshooting", "spl_query",
    "detection_rule", "incident_note", "incident_report", "ioc", "cve", "tool",
    "product", "vendor", "mitre", "lesson_learned", "checklist", "prompt",
    "report_template", "link",
]


class KItem(BaseModel):
    title: str
    item_type: str = "note"
    content: str = ""
    summary: str = ""
    category: str = ""
    tags: list[str] = []
    source: str = ""
    url: str = ""
    related_project_id: int | None = None
    related_jira: str = ""
    favorite: bool = False
    notes: str = ""


@router.get("/types")
def types(user: str = Depends(get_current_user)):
    return ITEM_TYPES


@router.get("")
def list_items(q: str = "", item_type: str = "", category: str = "",
               favorite: bool = False, db: Session = Depends(get_db),
               user: str = Depends(get_current_user)):
    query = db.query(KnowledgeItem)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(KnowledgeItem.title.ilike(like),
                                 KnowledgeItem.content.ilike(like),
                                 KnowledgeItem.summary.ilike(like)))
    if item_type:
        query = query.filter(KnowledgeItem.item_type == item_type)
    if category:
        query = query.filter(KnowledgeItem.category == category)
    if favorite:
        query = query.filter(KnowledgeItem.favorite.is_(True))
    rows = query.order_by(desc(KnowledgeItem.updated_at)).limit(200).all()
    return [
        {"id": r.id, "title": r.title, "item_type": r.item_type,
         "summary": r.summary, "category": r.category, "tags": r.tags,
         "favorite": r.favorite, "updated_at": r.updated_at}
        for r in rows
    ]


@router.get("/{item_id}")
def get_item(item_id: int, db: Session = Depends(get_db),
             user: str = Depends(get_current_user)):
    row = db.get(KnowledgeItem, item_id)
    if not row:
        raise HTTPException(404, "Item not found")
    return {c.name: getattr(row, c.name) for c in KnowledgeItem.__table__.columns}


@router.post("")
def create_item(item: KItem, db: Session = Depends(get_db),
                user: str = Depends(get_current_user)):
    row = KnowledgeItem(**item.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.put("/{item_id}")
def update_item(item_id: int, item: KItem, db: Session = Depends(get_db),
                user: str = Depends(get_current_user)):
    row = db.get(KnowledgeItem, item_id)
    if not row:
        raise HTTPException(404, "Item not found")
    for field, value in item.model_dump().items():
        setattr(row, field, value)
    db.commit()
    return {"ok": True}


@router.delete("/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db),
                user: str = Depends(get_current_user)):
    row = db.get(KnowledgeItem, item_id)
    if not row:
        raise HTTPException(404, "Item not found")
    db.delete(row)
    db.commit()
    return {"ok": True}
