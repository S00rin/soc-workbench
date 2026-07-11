"""Background job execution + status tracking (Background Processing section).

Single-user + lightweight: a small thread pool runs jobs; each job is a row in
the `jobs` table with pending/running/completed/failed status and retry support.
No Redis/Celery.
"""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from ..database import SessionLocal
from ..logging_config import get_logger
from ..models.core import Job

logger = get_logger(__name__)
_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="job")

# Remember each job's worker so it can be retried without re-passing the fn.
# In-process only (single-user app); cleared on restart.
_fns: dict[int, Callable[[], str]] = {}


def create_job(kind: str, name: str, ref_type: str = "", ref_id: int | None = None) -> int:
    db = SessionLocal()
    try:
        job = Job(kind=kind, name=name, status="pending", ref_type=ref_type, ref_id=ref_id)
        db.add(job)
        db.commit()
        db.refresh(job)
        return job.id
    finally:
        db.close()


def _run(job_id: int, fn: Callable[[], str]) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.attempts += 1
        db.commit()
        try:
            result = fn() or ""
            job.status = "completed"
            job.progress = 100
            job.result = str(result)[:5000]
            logger.info("Job %s (%s) completed", job_id, job.name)
        except Exception as e:  # noqa: BLE001
            job.status = "failed"
            job.error = str(e)[:2000]
            logger.exception("Job %s (%s) failed", job_id, job.name)
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def submit(kind: str, name: str, fn: Callable[[], str], ref_type: str = "",
           ref_id: int | None = None) -> int:
    """Create a job row and run `fn` in the background. Returns job id."""
    job_id = create_job(kind, name, ref_type, ref_id)
    _fns[job_id] = fn
    _executor.submit(_run, job_id, fn)
    return job_id


def retry(job_id: int) -> bool:
    """Re-dispatch a previously-submitted job. Returns False if unavailable."""
    fn = _fns.get(job_id)
    if fn is None:
        return False
    _executor.submit(_run, job_id, fn)
    return True
