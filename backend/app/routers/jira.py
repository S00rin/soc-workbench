"""Jira integration + analysis (Module 6).

All write operations require an explicit confirm=true and are recorded.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.entities import Analysis
from ..security import get_current_user
from ..services import llm
from ..services.jira_client import JiraClient, JiraConfig, JiraError, build_write_preview, summarize_issues
from ..services.settings_service import get_all_resolved, get_value

router = APIRouter(prefix="/api/jira", tags=["jira"])


def _client(db: Session) -> JiraClient:
    cfg = JiraConfig(
        base_url=get_value(db, "jira_base_url"),
        token=get_value(db, "jira_token"),
        username=get_value(db, "jira_username"),
        password=get_value(db, "jira_password"),
        verify_ssl=get_value(db, "jira_verify_ssl", "true").lower() == "true",
        timeout=int(get_value(db, "jira_timeout", "30") or 30),
    )
    return JiraClient(cfg)


@router.post("/test")
def test(db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    try:
        with _client(db) as c:
            return c.test_connection()
    except JiraError as e:
        raise HTTPException(400, str(e))


class JQLRequest(BaseModel):
    jql: str
    max_results: int = 50


@router.post("/search")
def search(req: JQLRequest, db: Session = Depends(get_db),
           user: str = Depends(get_current_user)):
    try:
        with _client(db) as c:
            data = c.search(req.jql, req.max_results)
    except JiraError as e:
        raise HTTPException(400, str(e))
    return {"summary": summarize_issues(data),
            "issues": [
                {"key": i["key"],
                 "summary": i["fields"].get("summary", ""),
                 "status": (i["fields"].get("status") or {}).get("name"),
                 "assignee": (i["fields"].get("assignee") or {}).get("displayName"),
                 "priority": (i["fields"].get("priority") or {}).get("name"),
                 "updated": i["fields"].get("updated")}
                for i in data.get("issues", [])
            ]}


@router.get("/issue/{key}")
def issue(key: str, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    try:
        with _client(db) as c:
            return c.get_issue(key)
    except JiraError as e:
        raise HTTPException(400, str(e))


class AnalyzeRequest(BaseModel):
    jql: str
    instruction: str = "Summarize activity, list risks, action items, and unassigned/overdue issues."
    max_results: int = 100


@router.post("/analyze")
def analyze(req: AnalyzeRequest, db: Session = Depends(get_db),
            user: str = Depends(get_current_user)):
    try:
        with _client(db) as c:
            data = c.search(req.jql, req.max_results)
    except JiraError as e:
        raise HTTPException(400, str(e))
    summary = summarize_issues(data)
    lines = [f"- {i['key']} [{(i['fields'].get('status') or {}).get('name')}] "
             f"{i['fields'].get('summary', '')} "
             f"(assignee: {(i['fields'].get('assignee') or {}).get('displayName', 'unassigned')})"
             for i in data.get("issues", [])]
    context = f"JQL: {req.jql}\nStats: {summary}\n\nIssues:\n" + "\n".join(lines[:150])
    cfg = llm.config_from_settings(get_all_resolved(db))
    result_text = ""
    if cfg.has_credentials:
        try:
            result_text = llm.complete(
                "You are a SOC/PM analyst. Analyze Jira issues. Do not invent data.",
                f"{req.instruction}\n\n{context}", cfg).text
        except llm.LLMError as e:
            result_text = f"_LLM unavailable: {e}_\n\n(Showing statistical summary only.)"
    else:
        result_text = "_No LLM configured; showing statistical summary only._"

    analysis = Analysis(kind="jira", title=f"Jira analysis: {req.jql[:60]}",
                        query=req.jql, input_summary=str(summary),
                        result=result_text, raw=summary, model=cfg.model)
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return {"analysis_id": analysis.id, "summary": summary, "result": result_text}


# --- Write operations (preview -> confirm) ---
class WriteRequest(BaseModel):
    action: str  # create | comment | transition | update
    target: str = ""  # issue key or project key
    fields: dict = {}
    body: str = ""
    transition_id: str = ""
    confirm: bool = False


@router.post("/write")
def write(req: WriteRequest, db: Session = Depends(get_db),
          user: str = Depends(get_current_user)):
    if not req.confirm:
        # Return the preview object for the UI to display.
        preview_fields = req.fields or ({"body": req.body} if req.body else {})
        return {"preview": build_write_preview(req.action, req.target, preview_fields)}
    try:
        with _client(db) as c:
            if req.action == "create":
                res = c.create_issue(req.fields)
            elif req.action == "comment":
                res = c.add_comment(req.target, req.body)
            elif req.action == "transition":
                res = c.transition(req.target, req.transition_id)
            elif req.action == "update":
                res = c.update_issue(req.target, req.fields)
            else:
                raise HTTPException(400, f"Unknown action: {req.action}")
    except JiraError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "result": res}
