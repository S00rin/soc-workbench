"""LLM analysis + provider test (Module 4)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.entities import Analysis
from ..security import get_current_user
from ..services import llm
from ..services.optimizer import estimate_tokens
from ..services.sensitive_data import protect
from ..services.settings_service import get_all_resolved

router = APIRouter(prefix="/api/llm", tags=["llm"])


class AnalyzeRequest(BaseModel):
    system: str = "You are a senior SOC analyst. Be concise and accurate."
    content: str
    protect_mode: str = "mask"  # mask | tokenize | remove | none
    title: str = "LLM analysis"
    save: bool = True


class EstimateRequest(BaseModel):
    content: str


@router.post("/estimate")
def estimate(req: EstimateRequest, user: str = Depends(get_current_user)):
    return {"token_estimate": estimate_tokens(req.content)}


@router.post("/test")
def test_provider(db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    cfg = llm.config_from_settings(get_all_resolved(db))
    if not cfg.has_credentials:
        raise HTTPException(
            400,
            "No LLM credentials configured. Set an API key in Settings → LLM, or "
            "select the 'claude_cli' provider to use the local Claude Code agent.",
        )
    try:
        result = llm.complete("You are a test.", "Reply with the single word OK.", cfg)
    except llm.LLMError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "model": result.model, "reply": result.text.strip()[:40]}


@router.post("/analyze")
def analyze(req: AnalyzeRequest, db: Session = Depends(get_db),
            user: str = Depends(get_current_user)):
    # Always protect before sending unless explicitly disabled.
    if req.protect_mode != "none":
        protected = protect(req.content, mode=req.protect_mode, db=db).text
    else:
        protected = req.content

    cfg = llm.config_from_settings(get_all_resolved(db))
    try:
        result = llm.complete(req.system, protected, cfg)
    except llm.LLMError as e:
        raise HTTPException(400, str(e))

    saved_id = None
    if req.save:
        analysis = Analysis(
            kind="llm", title=req.title, input_summary=protected[:500],
            result=result.text, model=result.model,
            token_estimate=result.input_tokens + result.output_tokens,
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        saved_id = analysis.id

    return {
        "result": result.text,
        "model": result.model,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "sent_content": protected,
        "analysis_id": saved_id,
    }


@router.get("/history")
def history(db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    rows = db.query(Analysis).order_by(desc(Analysis.created_at)).limit(100).all()
    return [
        {"id": r.id, "kind": r.kind, "title": r.title, "model": r.model,
         "token_estimate": r.token_estimate, "created_at": r.created_at}
        for r in rows
    ]


@router.get("/history/{analysis_id}")
def get_analysis(analysis_id: int, db: Session = Depends(get_db),
                 user: str = Depends(get_current_user)):
    row = db.get(Analysis, analysis_id)
    if not row:
        raise HTTPException(404, "Analysis not found")
    return {c.name: getattr(row, c.name) for c in Analysis.__table__.columns}
