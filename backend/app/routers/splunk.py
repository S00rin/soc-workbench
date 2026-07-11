"""Splunk integration (Module 7). Read-only search by default."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.entities import Analysis
from ..security import get_current_user
from ..services import llm
from ..services.settings_service import get_all_resolved, get_value
from ..services.splunk_client import SplunkClient, SplunkConfig, SplunkError

router = APIRouter(prefix="/api/splunk", tags=["splunk"])


def _client(db: Session) -> SplunkClient:
    allowed = [x.strip() for x in get_value(db, "splunk_allowed_indexes", "").split(",") if x.strip()]
    cfg = SplunkConfig(
        base_url=get_value(db, "splunk_base_url"),
        token=get_value(db, "splunk_token"),
        username=get_value(db, "splunk_username"),
        password=get_value(db, "splunk_password"),
        verify_ssl=get_value(db, "splunk_verify_ssl", "true").lower() == "true",
        timeout=int(get_value(db, "splunk_timeout", "60") or 60),
        allowed_indexes=allowed or None,
        max_results=int(get_value(db, "splunk_max_results", "1000") or 1000),
    )
    return SplunkClient(cfg)


@router.post("/test")
def test(db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    try:
        with _client(db) as c:
            return c.test_connection()
    except SplunkError as e:
        raise HTTPException(400, str(e))


class SearchRequest(BaseModel):
    spl: str
    earliest: str = "-24h"
    latest: str = "now"
    max_results: int | None = None


@router.post("/search")
def search(req: SearchRequest, db: Session = Depends(get_db),
           user: str = Depends(get_current_user)):
    try:
        with _client(db) as c:
            return c.search(req.spl, req.earliest, req.latest, req.max_results)
    except SplunkError as e:
        raise HTTPException(400, str(e))


@router.get("/saved")
def saved(db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    try:
        with _client(db) as c:
            return c.saved_searches()
    except SplunkError as e:
        raise HTTPException(400, str(e))


class AnalyzeRequest(BaseModel):
    spl: str
    earliest: str = "-24h"
    latest: str = "now"
    instruction: str = "Analyze these Splunk results: notable patterns, anomalies, and recommendations."


@router.post("/analyze")
def analyze(req: AnalyzeRequest, db: Session = Depends(get_db),
            user: str = Depends(get_current_user)):
    try:
        with _client(db) as c:
            data = c.search(req.spl, req.earliest, req.latest)
    except SplunkError as e:
        raise HTTPException(400, str(e))
    rows = data.get("results", [])[:100]
    context = f"SPL: {req.spl}\nResult count: {data.get('count')}\nFields: {data.get('fields')}\n\nSample rows:\n"
    context += "\n".join(str(r) for r in rows[:50])
    cfg = llm.config_from_settings(get_all_resolved(db))
    if cfg.has_credentials:
        try:
            result_text = llm.complete(
                "You are a Splunk/SOC analyst. Analyze results. Do not invent data.",
                f"{req.instruction}\n\n{context}", cfg).text
        except llm.LLMError as e:
            result_text = f"_LLM unavailable: {e}_"
    else:
        result_text = "_No LLM configured._"
    analysis = Analysis(kind="splunk", title=f"Splunk analysis: {req.spl[:60]}",
                        query=req.spl, input_summary=f"{data.get('count')} rows",
                        result=result_text, raw={"count": data.get("count")}, model=cfg.model)
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return {"analysis_id": analysis.id, "count": data.get("count"), "result": result_text}
