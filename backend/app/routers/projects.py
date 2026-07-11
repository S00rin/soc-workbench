"""Lightweight project management (Module 10)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.entities import Project
from ..security import get_current_user

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectIn(BaseModel):
    name: str
    customer: str = ""
    description: str = ""
    status: str = "active"
    start_date: str = ""
    end_date: str = ""
    manager: str = ""
    tech_owner: str = ""
    health: str = "green"
    progress: int = 0
    jira_project: str = ""
    splunk_env: str = ""
    risks: list = []
    issues: list = []
    milestones: list = []
    action_items: list = []
    notes: str = ""


@router.get("")
def list_projects(db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    rows = db.query(Project).order_by(desc(Project.updated_at)).all()
    return [{"id": r.id, "name": r.name, "customer": r.customer, "status": r.status,
             "health": r.health, "progress": r.progress, "manager": r.manager,
             "end_date": r.end_date} for r in rows]


@router.get("/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db),
                user: str = Depends(get_current_user)):
    row = db.get(Project, project_id)
    if not row:
        raise HTTPException(404, "Project not found")
    return {c.name: getattr(row, c.name) for c in Project.__table__.columns}


@router.post("")
def create_project(p: ProjectIn, db: Session = Depends(get_db),
                   user: str = Depends(get_current_user)):
    row = Project(**p.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.put("/{project_id}")
def update_project(project_id: int, p: ProjectIn, db: Session = Depends(get_db),
                   user: str = Depends(get_current_user)):
    row = db.get(Project, project_id)
    if not row:
        raise HTTPException(404, "Project not found")
    for field, value in p.model_dump().items():
        setattr(row, field, value)
    db.commit()
    return {"ok": True}


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db),
                   user: str = Depends(get_current_user)):
    row = db.get(Project, project_id)
    if not row:
        raise HTTPException(404, "Project not found")
    db.delete(row)
    db.commit()
    return {"ok": True}
