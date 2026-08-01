"""Unified chat API for Jira, Confluence and Wiki.js."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.atlassian import AtlassianConnection
from ..models.governance import ExternalConnection, IntegrationChatSession, IntegrationChatTurn
from ..security import AuthContext, get_auth_context
from ..services.atlassian_connections import safe_connection, scoped_connection
from ..services.integration_chat import (
    SUPPORTED_PROVIDERS, ChatExecutionError, execute_turn, scoped_session, session_dict, turn_dict,
)
from ..services.access_control import require_feature
from ..services.integration_history import audit
from ..services.wikijs_provider import safe_external_connection, scoped_wikijs_connection
from ..services.settings_service import get_value

router = APIRouter(prefix="/api/integrations", tags=["integration-chat"])


class SessionIn(BaseModel):
    provider: str = Field(pattern=r"^(jira|confluence|wikijs|splunk)$")
    connection_id: int = Field(ge=1)
    title: str = Field(default="New integration chat", max_length=240)
    scope_query: str = Field(default="", max_length=10000)


class TurnIn(BaseModel):
    prompt: str = Field(min_length=2, max_length=10000)
    query_override: str = Field(default="", max_length=10000)


class RenameIn(BaseModel):
    title: str = Field(min_length=2, max_length=240)


def _ensure_connection(db: Session, context: AuthContext, provider: str, connection_id: int) -> None:
    require_feature(db, context.tenant_id, context.role, f"integration.{provider}")
    try:
        if provider in {"jira", "confluence"}:
            row = scoped_connection(db, context, connection_id)
            if provider not in (row.products or []):
                raise HTTPException(409, f"{provider.title()} is not enabled on this connection")
        elif provider == "wikijs":
            scoped_wikijs_connection(db, context, connection_id)
        elif not get_value(db, "splunk_base_url"):
            raise HTTPException(409, "Splunk is not configured in Settings")
    except LookupError as error:
        raise HTTPException(404, str(error)) from error


@router.get("/connections")
def combined_connections(db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    items: list[dict] = []
    for row in db.query(AtlassianConnection).filter(AtlassianConnection.tenant_id == context.tenant_id).order_by(AtlassianConnection.name).all():
        safe = safe_connection(row)
        for product in row.products or []:
            items.append({**safe, "connection_id": row.id, "provider": product, "display_name": f"{row.name} · {product.title()}"})
    for row in db.query(ExternalConnection).filter(
        ExternalConnection.tenant_id == context.tenant_id,
        ExternalConnection.provider == "wikijs",
    ).order_by(ExternalConnection.name).all():
        safe = safe_external_connection(row)
        items.append({**safe, "connection_id": row.id, "display_name": f"{row.name} · Wiki.js"})
    if get_value(db, "splunk_base_url"):
        items.append({
            "connection_id": 1, "provider": "splunk", "name": "Splunk", "display_name": "Splunk",
            "base_url": get_value(db, "splunk_base_url"), "enabled": True, "sorin_enabled": True,
            "has_credentials": bool(get_value(db, "splunk_token") or get_value(db, "splunk_password")),
        })
    return items


@router.get("/chat/sessions")
def list_sessions(
    provider: str = "", search: str = "", page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100), db: Session = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
):
    query = db.query(IntegrationChatSession).filter(
        IntegrationChatSession.tenant_id == context.tenant_id,
        IntegrationChatSession.owner_user_id == context.username,
        IntegrationChatSession.status != "deleted",
    )
    if provider:
        if provider not in SUPPORTED_PROVIDERS:
            raise HTTPException(422, "Unsupported provider")
        query = query.filter(IntegrationChatSession.provider == provider)
    if search:
        query = query.filter(IntegrationChatSession.title.contains(search[:120]))
    total = query.count()
    rows = query.order_by(desc(IntegrationChatSession.updated_at)).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [session_dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/chat/sessions")
def create_session(payload: SessionIn, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    _ensure_connection(db, context, payload.provider, payload.connection_id)
    row = IntegrationChatSession(
        tenant_id=context.tenant_id, owner_user_id=context.username,
        provider=payload.provider, connection_id=payload.connection_id,
        title=payload.title.strip() or "New integration chat", scope_query=payload.scope_query.strip(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, context, "integration_chat.create", "chat_session", str(row.id), connection_id=payload.connection_id)
    return session_dict(row)


@router.get("/chat/sessions/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    try:
        row = scoped_session(db, context, session_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    turns = db.query(IntegrationChatTurn).filter(IntegrationChatTurn.session_id == row.id).order_by(IntegrationChatTurn.created_at).all()
    return {**session_dict(row), "turns": [turn_dict(turn) for turn in turns]}


@router.post("/chat/sessions/{session_id}/turns")
def add_turn(session_id: int, payload: TurnIn, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    try:
        session = scoped_session(db, context, session_id)
        require_feature(db, context.tenant_id, context.role, f"integration.{session.provider}")
        return turn_dict(execute_turn(db, context, session, payload.prompt, payload.query_override))
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ChatExecutionError as error:
        raise HTTPException(error.status_code, error.as_dict()) from error


@router.put("/chat/sessions/{session_id}")
def rename_session(session_id: int, payload: RenameIn, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    try:
        row = scoped_session(db, context, session_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    row.title = payload.title.strip()
    db.commit()
    return session_dict(row)


@router.delete("/chat/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    try:
        row = scoped_session(db, context, session_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    row.status = "deleted"
    db.commit()
    audit(db, context, "integration_chat.delete", "chat_session", str(row.id), connection_id=row.connection_id)
    return {"ok": True}
