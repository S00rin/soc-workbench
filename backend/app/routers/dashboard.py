"""Dashboard aggregation (Module 1)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.content import Document, IntelItem, KnowledgeItem
from ..models.core import Job
from ..models.entities import Analysis, IoC, Project, Report
from ..security import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _rows(db: Session, model, limit: int, order):
    return [
        {c.name: getattr(r, c.name) for c in model.__table__.columns
         if c.name not in ("original_text", "markdown", "protected_markdown",
                           "optimized_markdown", "sorin_analysis", "content", "raw")}
        for r in db.query(model).order_by(order).limit(limit).all()
    ]


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    active_projects = db.query(Project).filter(Project.status == "active").count()
    failed_jobs = (
        db.query(Job).filter(Job.status == "failed").order_by(desc(Job.updated_at)).limit(10).all()
    )
    return {
        "counts": {
            "active_projects": active_projects,
            "documents": db.query(Document).count(),
            "knowledge_items": db.query(KnowledgeItem).count(),
            "intel_items": db.query(IntelItem).count(),
            "iocs": db.query(IoC).count(),
            "reports": db.query(Report).count(),
            "analyses": db.query(Analysis).count(),
        },
        "recent_documents": _rows(db, Document, 5, desc(Document.created_at)),
        "recent_intel": _rows(db, IntelItem, 5, desc(IntelItem.created_at)),
        "recent_reports": _rows(db, Report, 5, desc(Report.created_at)),
        "recent_analyses": _rows(db, Analysis, 5, desc(Analysis.created_at)),
        "new_iocs": _rows(db, IoC, 8, desc(IoC.created_at)),
        "failed_jobs": [
            {"id": j.id, "name": j.name, "kind": j.kind, "error": j.error[:200]}
            for j in failed_jobs
        ],
        "scheduled_tasks": [
            {"name": "Daily database backup", "schedule": "02:00 UTC daily"},
        ],
    }
