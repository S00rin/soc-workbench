"""SOC Knowledge Base (Module 8, core CRUD + search)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.content import KnowledgeItem
from ..schemas import KnowledgeIn, KnowledgeOut
from ..security import get_current_user

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("", response_model=list[KnowledgeOut])
def list_items(
    q: str = "",
    item_type: str = "",
    category: str = "",
    tag: str = "",
    favorite: bool | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    query = db.query(KnowledgeItem)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                KnowledgeItem.title.ilike(like),
                KnowledgeItem.content.ilike(like),
                KnowledgeItem.summary.ilike(like),
            )
        )
    if item_type:
        query = query.filter(KnowledgeItem.item_type == item_type)
    if category:
        query = query.filter(KnowledgeItem.category == category)
    if favorite is not None:
        query = query.filter(KnowledgeItem.favorite.is_(favorite))
    items = query.order_by(KnowledgeItem.updated_at.desc()).limit(limit).all()
    if tag:
        items = [i for i in items if tag in (i.tags or [])]
    return items


@router.post("", response_model=KnowledgeOut)
def create_item(
    payload: KnowledgeIn,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    item = KnowledgeItem(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/{item_id}", response_model=KnowledgeOut)
def get_item(item_id: int, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    item = db.get(KnowledgeItem, item_id)
    if not item:
        raise HTTPException(404, "Knowledge item not found")
    return item


@router.put("/{item_id}", response_model=KnowledgeOut)
def update_item(
    item_id: int,
    payload: KnowledgeIn,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    item = db.get(KnowledgeItem, item_id)
    if not item:
        raise HTTPException(404, "Knowledge item not found")
    for k, v in payload.model_dump().items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    item = db.get(KnowledgeItem, item_id)
    if not item:
        raise HTTPException(404, "Knowledge item not found")
    db.delete(item)
    db.commit()
    return {"ok": True}
