"""Internet intelligence (Module 5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.content import IntelItem, IntelSource, KnowledgeItem
from ..security import get_current_user
from ..services import intel_collector as collector
from ..services import intel_ingest

router = APIRouter(prefix="/api/intel", tags=["intel"])


class CollectRequest(BaseModel):
    kind: str = "feed"  # feed | url
    source: str
    limit: int = 20
    summarize: bool = False  # use LLM for FA/EN summaries
    to_kb: bool = True       # auto-add to knowledge base
    to_iocs: bool = True     # auto-extract IoCs


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
    stats = intel_ingest.store_items(
        db, items, summarize=req.summarize, to_kb=req.to_kb, to_iocs=req.to_iocs)
    return {"collected": len(items), "new": stats["new"],
            "kb": stats["kb"], "iocs": stats["iocs"],
            "items": [{"id": r.id, "title": r.title, "category": r.category,
                       "relevance": r.relevance, "url": r.url} for r in stats["rows"]]}


class CollectAllRequest(BaseModel):
    limit: int = 20
    summarize: bool = False
    to_kb: bool = True
    to_iocs: bool = True


@router.post("/collect-all")
def collect_all(req: CollectAllRequest, db: Session = Depends(get_db),
                user: str = Depends(get_current_user)):
    """Collect from every enabled source; auto-ingest into KB + IoC list."""
    totals = intel_ingest.run_collection(
        db, limit=req.limit, summarize=req.summarize,
        to_kb=req.to_kb, to_iocs=req.to_iocs)
    return totals


# --- Source management ----------------------------------------------------

class SourceIn(BaseModel):
    name: str
    url: str = ""
    kind: str = "feed"  # feed | url | x | telegram
    category: str = "Other"
    enabled: bool = True
    notes: str = ""


class SourcePatch(BaseModel):
    name: str | None = None
    url: str | None = None
    kind: str | None = None
    category: str | None = None
    enabled: bool | None = None
    notes: str | None = None


@router.get("/sources")
def list_sources(db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    rows = db.query(IntelSource).order_by(IntelSource.category, IntelSource.name).all()
    return [{c.name: getattr(r, c.name) for c in IntelSource.__table__.columns}
            for r in rows]


@router.post("/sources")
def create_source(src: SourceIn, db: Session = Depends(get_db),
                  user: str = Depends(get_current_user)):
    row = IntelSource(**src.model_dump(), builtin=False,
                      requires_config=src.kind in ("x", "telegram") and not src.url)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.patch("/sources/{source_id}")
def patch_source(source_id: int, req: SourcePatch, db: Session = Depends(get_db),
                 user: str = Depends(get_current_user)):
    row = db.get(IntelSource, source_id)
    if not row:
        raise HTTPException(404, "Source not found")
    for field, value in req.model_dump(exclude_none=True).items():
        setattr(row, field, value)
    if row.url:  # once a placeholder is given a URL it no longer needs config
        row.requires_config = False
    db.commit()
    return {"ok": True}


@router.delete("/sources/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db),
                  user: str = Depends(get_current_user)):
    row = db.get(IntelSource, source_id)
    if not row:
        raise HTTPException(404, "Source not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


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
