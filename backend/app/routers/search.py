"""Global keyword search across modules (Search section)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.content import Document, IntelItem, KnowledgeItem
from ..models.entities import IoC, Project, Prompt, Report
from ..security import get_current_user

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search(q: str, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    if not q or len(q) < 2:
        return {"results": []}
    like = f"%{q}%"
    results = []

    for r in db.query(Project).filter(or_(Project.name.ilike(like),
                                          Project.description.ilike(like))).limit(20):
        results.append({"type": "project", "id": r.id, "title": r.name, "snippet": r.customer})
    for r in db.query(KnowledgeItem).filter(or_(KnowledgeItem.title.ilike(like),
                                                KnowledgeItem.content.ilike(like))).limit(20):
        results.append({"type": "knowledge", "id": r.id, "title": r.title, "snippet": r.summary})
    for r in db.query(IntelItem).filter(IntelItem.title.ilike(like)).limit(20):
        results.append({"type": "intel", "id": r.id, "title": r.title, "snippet": r.source})
    for r in db.query(IoC).filter(IoC.value.ilike(like)).limit(20):
        results.append({"type": "ioc", "id": r.id, "title": r.value, "snippet": r.ioc_type})
    for r in db.query(Report).filter(Report.title.ilike(like)).limit(20):
        results.append({"type": "report", "id": r.id, "title": r.title, "snippet": r.report_type})
    for r in db.query(Document).filter(Document.title.ilike(like)).limit(20):
        results.append({"type": "document", "id": r.id, "title": r.title, "snippet": r.source_type})
    for r in db.query(Prompt).filter(Prompt.name.ilike(like)).limit(20):
        results.append({"type": "prompt", "id": r.id, "title": r.name, "snippet": r.category})

    return {"query": q, "count": len(results), "results": results}
