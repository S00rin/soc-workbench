"""Job status + retry (Background Processing section)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.core import Job
from ..schemas import JobOut
from ..security import get_current_user
from ..services import jobs as job_svc

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(
    status: str = "",
    kind: str = "",
    limit: int = 100,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    query = db.query(Job)
    if status:
        query = query.filter(Job.status == status)
    if kind:
        query = query.filter(Job.kind == kind)
    return query.order_by(Job.created_at.desc()).limit(limit).all()


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/{job_id}/retry", response_model=JobOut)
def retry_job(job_id: int, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if not job_svc.retry(job_id):
        raise HTTPException(
            409,
            "This job cannot be retried (its worker is no longer in memory — "
            "it was created before the last restart). Re-run the original action.",
        )
    job.status = "pending"
    job.error = ""
    db.commit()
    db.refresh(job)
    return job
