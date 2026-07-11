"""Internet intelligence (Module 5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.content import IntelItem, KnowledgeItem
from ..security import get_current_user
from ..services import intel_collector as collector
from ..services import llm
from ..services.settings_service import get_all_resolved

router = APIRouter(prefix="/api/intel", tags=["intel"])


class CollectRequest(BaseModel):
    kind: str = "feed"  # feed | url
    source: str
    limit: int = 20
    summarize: bool = False  # use LLM for FA/EN summaries


def _dedupe_and_store(db: Session, items, summarize: bool):
    stored = []
    cfg = llm.config_from_settings(get_all_resolved(db)) if summarize else None
    for it in items:
        exists = db.query(IntelItem).filter(IntelItem.content_hash == it.content_hash).first()
        if exists:
            continue
        summary_fa = it.summary_fa
        summary_en = it.summary_en
        if summarize and cfg and cfg.has_credentials and it.content:
            try:
                out = llm.complete(
                    "Summarize the article in two short paragraphs: first in English, "
                    "then in Persian (فارسی). Separate them with '---'.",
                    it.content[:6000], cfg).text
                parts = out.split("---")
                summary_en = parts[0].strip()
                summary_fa = parts[1].strip() if len(parts) > 1 else summary_fa
            except llm.LLMError:
                pass
        row = IntelItem(
            title=it.title, original_title=it.original_title, source=it.source,
            url=it.url, published_at=it.published_at, content=it.content,
            category=it.category, tags=it.tags, entities=it.entities,
            summary_en=summary_en, summary_fa=summary_fa,
            relevance=it.relevance, content_hash=it.content_hash,
        )
        db.add(row)
        stored.append(row)
    db.commit()
    return stored


@router.post("/collect")
def collect(req: CollectRequest, db: Session = Depends(get_db),
            user: str = Depends(get_current_user)):
    try:
        if req.kind == "url":
            items = [collector.collect_url(req.source)]
        else:
            items = collector.collect_feed(req.source, req.limit)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Collection failed: {e}")
    stored = _dedupe_and_store(db, items, req.summarize)
    return {"collected": len(items), "new": len(stored),
            "items": [{"id": r.id, "title": r.title, "category": r.category,
                       "relevance": r.relevance, "url": r.url} for r in stored]}


@router.get("")
def list_items(category: str = "", saved: bool = False, db: Session = Depends(get_db),
               user: str = Depends(get_current_user)):
    q = db.query(IntelItem)
    if category:
        q = q.filter(IntelItem.category == category)
    if saved:
        q = q.filter(IntelItem.saved.is_(True))
    rows = q.order_by(desc(IntelItem.created_at)).limit(200).all()
    return [{"id": r.id, "title": r.title, "source": r.source, "url": r.url,
             "category": r.category, "relevance": r.relevance, "tags": r.tags,
             "read": r.read, "saved": r.saved, "published_at": r.published_at,
             "summary_en": r.summary_en, "summary_fa": r.summary_fa}
            for r in rows]


@router.get("/{item_id}")
def get_item(item_id: int, db: Session = Depends(get_db),
             user: str = Depends(get_current_user)):
    row = db.get(IntelItem, item_id)
    if not row:
        raise HTTPException(404, "Not found")
    row.read = True
    db.commit()
    return {c.name: getattr(row, c.name) for c in IntelItem.__table__.columns}


class PatchRequest(BaseModel):
    saved: bool | None = None
    read: bool | None = None
    notes: str | None = None


@router.patch("/{item_id}")
def patch_item(item_id: int, req: PatchRequest, db: Session = Depends(get_db),
               user: str = Depends(get_current_user)):
    row = db.get(IntelItem, item_id)
    if not row:
        raise HTTPException(404, "Not found")
    for field, value in req.model_dump(exclude_none=True).items():
        setattr(row, field, value)
    db.commit()
    return {"ok": True}


@router.post("/{item_id}/to-knowledge")
def to_knowledge(item_id: int, db: Session = Depends(get_db),
                 user: str = Depends(get_current_user)):
    row = db.get(IntelItem, item_id)
    if not row:
        raise HTTPException(404, "Not found")
    ki = KnowledgeItem(title=row.title, item_type="article",
                       content=row.content or row.summary_en, summary=row.summary_en,
                       category=row.category, tags=row.tags, source=row.source, url=row.url)
    db.add(ki)
    db.commit()
    db.refresh(ki)
    return {"knowledge_id": ki.id}
