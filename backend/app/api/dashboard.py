"""Main dashboard aggregation (Module 1)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.content import Document, IntelItem, KnowledgeItem
from ..models.core import Job
from ..models.entities import IoC, Project, Report
from ..schemas import DashboardOut
from ..security import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    counts = {
        "projects": db.query(Project).count(),
        "documents": db.query(Document).count(),
        "knowledge": db.query(KnowledgeItem).count(),
        "iocs": db.query(IoC).count(),
        "reports": db.query(Report).count(),
        "intel": db.query(IntelItem).count(),
        "jobs_failed": db.query(Job).filter(Job.status == "failed").count(),
        "jobs_running": db.query(Job).filter(Job.status.in_(["running", "pending"])).count(),
    }

    active_projects = [
        {"id": p.id, "name": p.name, "customer": p.customer, "status": p.status,
         "health": p.health, "progress": p.progress}
        for p in db.query(Project).filter(Project.status == "active")
        .order_by(Project.updated_at.desc()).limit(6)
    ]
    recent_documents = [
        {"id": d.id, "title": d.title, "source_type": d.source_type,
         "created_at": d.created_at.isoformat()}
        for d in db.query(Document).order_by(Document.created_at.desc()).limit(6)
    ]
    recent_knowledge = [
        {"id": k.id, "title": k.title, "item_type": k.item_type,
         "updated_at": k.updated_at.isoformat()}
        for k in db.query(KnowledgeItem).order_by(KnowledgeItem.updated_at.desc()).limit(6)
    ]
    recent_iocs = [
        {"id": i.id, "value": i.value, "ioc_type": i.ioc_type, "severity": i.severity,
         "created_at": i.created_at.isoformat()}
        for i in db.query(IoC).order_by(IoC.created_at.desc()).limit(8)
    ]
    recent_reports = [
        {"id": r.id, "title": r.title, "report_type": r.report_type, "status": r.status,
         "created_at": r.created_at.isoformat()}
        for r in db.query(Report).order_by(Report.created_at.desc()).limit(6)
    ]
    failed_jobs = [
        {"id": j.id, "name": j.name, "kind": j.kind, "error": j.error,
         "created_at": j.created_at.isoformat()}
        for j in db.query(Job).filter(Job.status == "failed")
        .order_by(Job.created_at.desc()).limit(6)
    ]
    recent_jobs = [
        {"id": j.id, "name": j.name, "kind": j.kind, "status": j.status,
         "created_at": j.created_at.isoformat()}
        for j in db.query(Job).order_by(Job.created_at.desc()).limit(8)
    ]

    return DashboardOut(
        counts=counts,
        active_projects=active_projects,
        recent_documents=recent_documents,
        recent_knowledge=recent_knowledge,
        recent_iocs=recent_iocs,
        recent_reports=recent_reports,
        failed_jobs=failed_jobs,
        recent_jobs=recent_jobs,
    )
