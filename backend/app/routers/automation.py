"""APIs for scheduled intelligence sources and safe Claude Code tasks."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.automation import ClaudeTask, IntelSource, IoCSource
from ..security import get_current_user
from ..services import claude_tasks, intelligence_automation

router = APIRouter(prefix="/api/automation", tags=["automation"])


class IntelSourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str
    source_type: str = "rss"
    category: str = "Threat Intelligence"
    trust_score: float = Field(default=0.7, ge=0, le=1)
    interval_minutes: int = Field(default=60, ge=15)
    enabled: bool = True
    auto_save_kb: bool = True
    auto_extract_iocs: bool = True
    summarize: bool = False


class IoCSourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str
    adapter: str
    trust_score: float = Field(default=0.7, ge=0, le=1)
    interval_minutes: int = Field(default=60, ge=15)
    enabled: bool = True
    configuration: dict = Field(default_factory=dict)


class ClaudeTaskIn(BaseModel):
    title: str = "Claude Code task"
    prompt: str = Field(min_length=1)
    workspace: str
    mode: str = "read-only"
    timeout_seconds: int = Field(default=600, ge=30, le=3600)
    max_turns: int = Field(default=10, ge=1, le=50)


def _row(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


@router.get("/intel-sources")
def list_intel_sources(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    return [_row(x) for x in db.query(IntelSource).order_by(IntelSource.name).all()]


@router.post("/intel-sources")
def create_intel_source(payload: IntelSourceIn, db: Session = Depends(get_db),
                        _: str = Depends(get_current_user)):
    row = IntelSource(**payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return _row(row)


@router.put("/intel-sources/{source_id}")
def update_intel_source(source_id: int, payload: IntelSourceIn,
                        db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    row = db.get(IntelSource, source_id)
    if not row:
        raise HTTPException(404, "Intel source not found")
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    db.commit(); db.refresh(row)
    return _row(row)


@router.delete("/intel-sources/{source_id}")
def delete_intel_source(source_id: int, db: Session = Depends(get_db),
                        _: str = Depends(get_current_user)):
    row = db.get(IntelSource, source_id)
    if not row:
        raise HTTPException(404, "Intel source not found")
    db.delete(row); db.commit()
    return {"ok": True}


@router.post("/intel-sources/{source_id}/run")
def run_intel_source(source_id: int, db: Session = Depends(get_db),
                     _: str = Depends(get_current_user)):
    row = db.get(IntelSource, source_id)
    if not row:
        raise HTTPException(404, "Intel source not found")
    try:
        return intelligence_automation.collect_intel_source(db, row)
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.get("/ioc-sources")
def list_ioc_sources(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    intelligence_automation.seed_default_sources(db)
    return [_row(x) for x in db.query(IoCSource).order_by(IoCSource.name).all()]


@router.post("/ioc-sources")
def create_ioc_source(payload: IoCSourceIn, db: Session = Depends(get_db),
                      _: str = Depends(get_current_user)):
    if payload.adapter not in intelligence_automation.ADAPTERS:
        raise HTTPException(400, "Unsupported adapter")
    row = IoCSource(**payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return _row(row)


@router.put("/ioc-sources/{source_id}")
def update_ioc_source(source_id: int, payload: IoCSourceIn,
                      db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    row = db.get(IoCSource, source_id)
    if not row:
        raise HTTPException(404, "IoC source not found")
    if payload.adapter not in intelligence_automation.ADAPTERS:
        raise HTTPException(400, "Unsupported adapter")
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    db.commit(); db.refresh(row)
    return _row(row)


@router.delete("/ioc-sources/{source_id}")
def delete_ioc_source(source_id: int, db: Session = Depends(get_db),
                      _: str = Depends(get_current_user)):
    row = db.get(IoCSource, source_id)
    if not row:
        raise HTTPException(404, "IoC source not found")
    db.delete(row); db.commit()
    return {"ok": True}


@router.post("/ioc-sources/{source_id}/run")
def run_ioc_source(source_id: int, db: Session = Depends(get_db),
                   _: str = Depends(get_current_user)):
    row = db.get(IoCSource, source_id)
    if not row:
        raise HTTPException(404, "IoC source not found")
    try:
        return intelligence_automation.collect_ioc_source(db, row)
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.post("/knowledge-to-iocs")
def knowledge_to_iocs(item_id: int | None = None, db: Session = Depends(get_db),
                      _: str = Depends(get_current_user)):
    return intelligence_automation.scan_knowledge_base(db, item_id=item_id)


@router.post("/run-all")
def run_all(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    return intelligence_automation.run_all(db, force=True)\n\n\n@router.get("/claude-tasks")
def list_claude_tasks(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    rows = db.query(ClaudeTask).order_by(ClaudeTask.created_at.desc()).limit(100).all()
    return [_row(x) for x in rows]


@router.get("/claude-tasks/{task_id}")
def get_claude_task(task_id: int, db: Session = Depends(get_db),
                    _: str = Depends(get_current_user)):
    row = db.get(ClaudeTask, task_id)
    if not row:
        raise HTTPException(404, "Claude task not found")
    return _row(row)


@router.post("/claude-tasks")
def create_claude_task(payload: ClaudeTaskIn, db: Session = Depends(get_db),
                       _: str = Depends(get_current_user)):
    if payload.mode not in {"plan", "read-only", "edit"}:
        raise HTTPException(400, "Mode must be plan, read-only, or edit")
    try:
        claude_tasks._allowed_workspace(payload.workspace)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    row = ClaudeTask(**payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    claude_tasks.submit(row.id)
    return _row(row)
