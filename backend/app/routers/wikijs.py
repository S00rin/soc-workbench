"""Wiki.js connection management and read APIs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.governance import ExternalConnection
from ..security import AuthContext, get_auth_context, require_admin
from ..services.integration_history import audit
from ..services.wikijs_provider import (
    WikiJSError, WikiJSProvider, safe_external_connection, scoped_wikijs_connection,
    update_test_state, upsert_wikijs_connection,
)

router = APIRouter(prefix="/api/wikijs", tags=["wikijs"])


class WikiConnectionIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    base_url: str = Field(min_length=8, max_length=500)
    api_token: str = Field(default="", max_length=4000)
    verify_ssl: bool = True
    timeout: int = Field(default=30, ge=5, le=120)
    enabled: bool = True
    sorin_enabled: bool = True


class WikiSearchIn(BaseModel):
    query: str = Field(default="", max_length=500)
    limit: int = Field(default=50, ge=1, le=100)


def _provider(row: ExternalConnection) -> WikiJSProvider:
    try:
        return WikiJSProvider(row)
    except WikiJSError as error:
        raise HTTPException(error.status_code or 422, error.as_dict()) from error


def _raise_wiki(error: WikiJSError) -> None:
    raise HTTPException(error.status_code or 502, error.as_dict()) from error


@router.get("/connections")
def list_connections(db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    rows = db.query(ExternalConnection).filter(
        ExternalConnection.tenant_id == context.tenant_id,
        ExternalConnection.provider == "wikijs",
    ).order_by(desc(ExternalConnection.updated_at)).all()
    return [safe_external_connection(row) for row in rows]


@router.post("/connections")
def create_connection(payload: WikiConnectionIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    if not payload.api_token or payload.api_token == "********":
        raise HTTPException(422, "API token is required for a new Wiki.js connection")
    try:
        row = upsert_wikijs_connection(db, context, payload.model_dump())
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "A Wiki.js connection with this name already exists") from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    audit(db, context, "wikijs.connection.create", "external_connection", str(row.id))
    return safe_external_connection(row)


@router.put("/connections/{connection_id}")
def update_connection(connection_id: int, payload: WikiConnectionIn, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    try:
        row = scoped_wikijs_connection(db, context, connection_id)
        row = upsert_wikijs_connection(db, context, payload.model_dump(), row)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    audit(db, context, "wikijs.connection.update", "external_connection", str(row.id))
    return safe_external_connection(row)


@router.delete("/connections/{connection_id}")
def delete_connection(connection_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(require_admin)):
    try:
        row = scoped_wikijs_connection(db, context, connection_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    db.delete(row)
    db.commit()
    audit(db, context, "wikijs.connection.delete", "external_connection", str(connection_id))
    return {"ok": True}


@router.post("/connections/{connection_id}/test")
def test_connection(connection_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    try:
        row = scoped_wikijs_connection(db, context, connection_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    provider = _provider(row)
    try:
        capabilities = provider.capability_preflight()
    finally:
        provider.close()
    update_test_state(db, row, capabilities)
    audit(db, context, "wikijs.connection.test", "external_connection", str(row.id), status="success" if capabilities["can_connect"]["allowed"] else "failed")
    return {"connection": safe_external_connection(row), "capabilities": capabilities}


@router.post("/connections/{connection_id}/search")
def search_pages(connection_id: int, payload: WikiSearchIn, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    try:
        row = scoped_wikijs_connection(db, context, connection_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    provider = _provider(row)
    try:
        pages = provider.search_pages(payload.query, payload.limit)
    except WikiJSError as error:
        _raise_wiki(error)
    finally:
        provider.close()
    return {"items": pages, "count": len(pages)}


@router.get("/connections/{connection_id}/pages/{page_id}")
def page(connection_id: int, page_id: int = Path(ge=1), db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    try:
        row = scoped_wikijs_connection(db, context, connection_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    provider = _provider(row)
    try:
        return provider.get_page(page_id)
    except WikiJSError as error:
        _raise_wiki(error)
    finally:
        provider.close()
