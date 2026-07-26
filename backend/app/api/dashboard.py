"""Main dashboard aggregation (Module 1)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.content import Document, IntelItem, KnowledgeItem
from ..models.core import Job
from ..models.entities import IoC, Project, Report
from ..models.atlassian import AtlassianConnection
from ..models.governance import ExternalConnection, FeaturePolicy, IntegrationChatSession, UserAccount, UserActivity
from ..schemas import DashboardOut
from ..security import AuthContext, get_auth_context
from ..services.access_control import policy_state

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    counts = {
        "projects": db.query(Project).count(),
        "documents": db.query(Document).count(),
        "knowledge": db.query(KnowledgeItem).count(),
        "iocs": db.query(IoC).count(),
        "reports": db.query(Report).count(),
        "intel": db.query(IntelItem).count(),
        "jobs_failed": db.query(Job).filter(Job.status == "failed").count(),
        "jobs_running": db.query(Job).filter(Job.status.in_(["running", "pending"])).count(),
        "active_projects": db.query(Project).filter(Project.status == "active").count(),
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

    atlassian_rows = db.query(AtlassianConnection).filter(AtlassianConnection.tenant_id == context.tenant_id).all()
    external_rows = db.query(ExternalConnection).filter(ExternalConnection.tenant_id == context.tenant_id).all()
    connectors = [*atlassian_rows, *external_rows]
    integration_health = {
        "total": len(connectors),
        "connected": sum(1 for row in connectors if row.enabled and row.last_success_at and not row.last_error_code),
        "attention": sum(1 for row in connectors if row.last_error_code or not row.enabled),
        "chats": db.query(IntegrationChatSession).filter(
            IntegrationChatSession.tenant_id == context.tenant_id,
            IntegrationChatSession.status != "deleted",
        ).count(),
        "items": [
            {"name": row.name, "provider": "atlassian" if isinstance(row, AtlassianConnection) else row.provider,
             "enabled": row.enabled, "last_success_at": row.last_success_at,
             "error_code": row.last_error_code, "error_summary": row.last_error_summary}
            for row in connectors[:8]
        ],
    }
    now = datetime.now(timezone.utc)
    policies = db.query(FeaturePolicy).filter(FeaturePolicy.tenant_id == context.tenant_id).all()
    feature_states = [(row, policy_state(row, now=now)) for row in policies]
    feature_health = {
        "active": sum(1 for _, state in feature_states if state["active"]),
        "unavailable": sum(1 for _, state in feature_states if not state["active"]),
        "expiring_soon": [
            {"key": row.feature_key, "expires_at": row.expires_at}
            for row, state in feature_states
            if state["active"] and row.expires_at and now < (row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)) <= now + timedelta(days=30)
        ],
    }
    user_summary = {
        "total": db.query(UserAccount).filter(UserAccount.tenant_id == context.tenant_id).count(),
        "active": db.query(UserAccount).filter(UserAccount.tenant_id == context.tenant_id, UserAccount.active.is_(True)).count(),
    }
    activity_query = db.query(UserActivity).filter(UserActivity.tenant_id == context.tenant_id)
    if context.role != "admin":
        activity_query = activity_query.filter(UserActivity.actor_user_id == context.username)
    recent_activity = [
        {"id": row.id, "actor": row.actor_user_id, "module": row.module_key, "action": row.action,
         "status_code": row.status_code, "duration_ms": row.duration_ms, "created_at": row.created_at}
        for row in activity_query.order_by(UserActivity.created_at.desc()).limit(10).all()
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
        integration_health=integration_health,
        feature_health=feature_health,
        user_summary=user_summary,
        recent_activity=recent_activity,
    )
