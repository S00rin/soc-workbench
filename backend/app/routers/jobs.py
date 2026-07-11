"""Job status + retry (Background Processing section)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.core import Job
from ..security import get_current_user
from ..services import jobs as job_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs(status: str = "", db: Session = Depends(get_db),
              user: str = Depends(get_current_user)):
    q = db.query(Job)
    if status:
        q = q.filter(Job.status == status)
    rows = q.order_by(desc(Job.created_at)).limit(100).all()
    return [{c.name: getattr(r, c.name) for c in Job.__table__.columns} for r in rows]


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db),
            user: str = Depends(get_current_user)):
    row = db.get(Job, job_id)
    if not row:
        raise HTTPException(404, "Job not found")
    return {c.name: getattr(row, c.name) for c in Job.__table__.columns}


@router.post("/{job_id}/retry")
def retry_job(job_id: int, db: Session = Depends(get_db),
              user: str = Depends(get_current_user)):
    row = db.get(Job, job_id)
    if not row:
        raise HTTPException(404, "Job not found")
    if not job_service.retry(job_id):
        raise HTTPException(
            400, "Job cannot be retried in-process (function not registered; "
            "restart clears the registry). Re-run the original action.")
    return {"ok": True}
