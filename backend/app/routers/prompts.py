"""Prompt library (Module 13)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.entities import Prompt
from ..security import get_current_user
from ..services import llm
from ..services.settings_service import get_all_resolved

router = APIRouter(prefix="/api/prompts", tags=["prompts"])

CATEGORIES = ["Jira analysis", "Splunk analysis", "Incident analysis",
              "Report generation", "Summarization", "Translation",
              "Internet intelligence", "IoC analysis", "Project management", "Custom"]


class PromptIn(BaseModel):
    name: str
    category: str = "Custom"
    description: str = ""
    system_prompt: str = ""
    user_template: str = ""
    variables: list[str] = []
    model: str = ""
    max_tokens: int = 0
    language: str = "en"
    favorite: bool = False


@router.get("/categories")
def categories(user: str = Depends(get_current_user)):
    return CATEGORIES


@router.get("")
def list_prompts(category: str = "", db: Session = Depends(get_db),
                 user: str = Depends(get_current_user)):
    q = db.query(Prompt)
    if category:
        q = q.filter(Prompt.category == category)
    rows = q.order_by(desc(Prompt.updated_at)).all()
    return [{c.name: getattr(r, c.name) for c in Prompt.__table__.columns} for r in rows]


@router.post("")
def create_prompt(p: PromptIn, db: Session = Depends(get_db),
                  user: str = Depends(get_current_user)):
    row = Prompt(**p.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.put("/{prompt_id}")
def update_prompt(prompt_id: int, p: PromptIn, db: Session = Depends(get_db),
                  user: str = Depends(get_current_user)):
    row = db.get(Prompt, prompt_id)
    if not row:
        raise HTTPException(404, "Prompt not found")
    for field, value in p.model_dump().items():
        setattr(row, field, value)
    db.commit()
    return {"ok": True}


@router.delete("/{prompt_id}")
def delete_prompt(prompt_id: int, db: Session = Depends(get_db),
                  user: str = Depends(get_current_user)):
    row = db.get(Prompt, prompt_id)
    if not row:
        raise HTTPException(404, "Prompt not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


class TestRequest(BaseModel):
    system_prompt: str = ""
    user_prompt: str
    variables: dict = {}


@router.post("/{prompt_id}/test")
def test_prompt(prompt_id: int, req: TestRequest, db: Session = Depends(get_db),
                user: str = Depends(get_current_user)):
    row = db.get(Prompt, prompt_id)
    if not row:
        raise HTTPException(404, "Prompt not found")
    user_prompt = req.user_prompt
    for k, v in req.variables.items():
        user_prompt = user_prompt.replace("{{" + k + "}}", str(v))
    cfg = llm.config_from_settings(get_all_resolved(db))
    try:
        result = llm.complete(req.system_prompt or row.system_prompt, user_prompt, cfg)
    except llm.LLMError as e:
        raise HTTPException(400, str(e))
    row.usage_count += 1
    db.commit()
    return {"result": result.text, "model": result.model,
            "tokens": result.input_tokens + result.output_tokens}
