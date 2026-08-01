"""Input and data processing (Module 2)."""
from __future__ import annotations

import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models.content import Document, KnowledgeItem
from ..security import get_current_user
from ..services import document_processing as dp
from ..services import extract
from ..services.sensitive_data import protect

router = APIRouter(prefix="/api/inputs", tags=["inputs"])
settings = get_settings()


class TextProcessRequest(BaseModel):
    title: str = "Untitled"
    content: str = ""
    url: str = ""
    kind: str = "text"  # text | html | csv | json | markdown | url
    protection_mode: str = "mask"
    optimization_mode: str = "balanced"
    max_tokens: int | None = None


class PreviewRequest(BaseModel):
    content: str
    mode: str = "mask"


def _persist(db: Session, source_type: str, source_ref: str, processed, stored_path=""):
    doc = Document(
        title=processed.title,
        source_type=source_type,
        source_ref=source_ref,
        stored_path=stored_path,
        original_text=processed.original_text,
        markdown=processed.markdown,
        protected_markdown=processed.protected_markdown,
        optimized_markdown=processed.optimized_markdown,
        summary=processed.summary,
        entities=processed.entities,
        protection_mode=processed.protection_mode,
        optimization_mode=processed.optimization_mode,
        token_estimate=processed.token_estimate,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.post("/preview-protected")
def preview_protected(req: PreviewRequest, db: Session = Depends(get_db),
                      user: str = Depends(get_current_user)):
    """Show the EXACT protected content that would be sent to an LLM."""
    result = protect(req.content, mode=req.mode, db=db)
    return {"protected": result.text, "counts": result.counts,
            "detections": len(result.detections)}


@router.post("/process-text")
def process_text(req: TextProcessRequest, db: Session = Depends(get_db),
                 user: str = Depends(get_current_user)):
    content = req.content
    source_type = req.kind
    source_ref = ""
    if req.kind == "url" or req.url:
        source_type = "url"
        source_ref = req.url
        try:
            with httpx.Client(timeout=25, follow_redirects=True) as c:
                r = c.get(req.url, headers={"User-Agent": "SOC-Workbench/1.0"})
                r.raise_for_status()
                content = r.text
        except httpx.HTTPError as e:
            raise HTTPException(400, f"Could not fetch URL: {e}")
        kind = "html"
    else:
        kind = req.kind if req.kind in ("html", "csv", "json") else "text"
    try:
        processed = dp.process(
            raw_text=content, kind=kind, title=req.title or "Untitled",
            protection_mode=req.protection_mode,
            optimization_mode=req.optimization_mode,
            max_tokens=req.max_tokens, db=db, token_scope=f"doc-{uuid.uuid4().hex[:8]}",
        )
    except (extract.ExtractionError, ValueError) as e:
        raise HTTPException(400, str(e))
    doc = _persist(db, source_type, source_ref, processed)
    return {"id": doc.id, **processed.to_dict()}


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    protection_mode: str = Form("mask"),
    optimization_mode: str = Form("balanced"),
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
):
    ext = Path(file.filename or "file").suffix.lower()
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = settings.uploads_dir / stored_name
    data = await file.read()
    dest.write_bytes(data)
    try:
        processed = dp.process(
            file_path=dest, title=file.filename or "Uploaded file",
            protection_mode=protection_mode, optimization_mode=optimization_mode,
            db=db, token_scope=f"file-{stored_name[:8]}",
        )
    except extract.ExtractionError as e:
        raise HTTPException(400, str(e))
    doc = _persist(db, "file", file.filename or "", processed, stored_name)
    doc.mime = file.content_type or ""
    db.commit()
    return {"id": doc.id, **processed.to_dict()}


@router.get("")
def list_docs(db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    docs = db.query(Document).order_by(desc(Document.created_at)).limit(100).all()
    return [
        {"id": d.id, "title": d.title, "source_type": d.source_type,
         "summary": d.summary, "token_estimate": d.token_estimate,
         "created_at": d.created_at, "status": d.status}
        for d in docs
    ]


@router.get("/{doc_id}")
def get_doc(doc_id: int, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return {c.name: getattr(doc, c.name) for c in Document.__table__.columns}


class UpdateDocRequest(BaseModel):
    markdown: str | None = None
    protected_markdown: str | None = None
    optimized_markdown: str | None = None
    sorin_analysis: str | None = None
    summary: str | None = None


@router.put("/{doc_id}")
def update_doc(doc_id: int, req: UpdateDocRequest, db: Session = Depends(get_db),
               user: str = Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    for field, value in req.model_dump(exclude_none=True).items():
        setattr(doc, field, value)
    db.commit()
    return {"ok": True}


@router.post("/{doc_id}/to-knowledge")
def to_knowledge(doc_id: int, db: Session = Depends(get_db),
                 user: str = Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    item = KnowledgeItem(
        title=doc.title, item_type="note",
        content=doc.protected_markdown or doc.markdown,
        summary=doc.summary, source=doc.source_ref,
        tags=doc.entities.get("keywords", [])[:8] if doc.entities else [],
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"knowledge_id": item.id}


@router.delete("/{doc_id}")
def delete_doc(doc_id: int, db: Session = Depends(get_db),
               user: str = Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.stored_path:
        fp = settings.uploads_dir / doc.stored_path
        if fp.exists():
            fp.unlink()
    db.delete(doc)
    db.commit()
    return {"ok": True}
