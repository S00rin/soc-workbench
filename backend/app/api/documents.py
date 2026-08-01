"""Input & Data Processing (Module 2) + LLM analysis (Module 4)."""
from __future__ import annotations

import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..logging_config import get_logger
from ..models.content import Document, KnowledgeItem
from ..models.entities import Analysis
from ..schemas import (
    AnalyzeIn,
    DocumentListItem,
    DocumentOut,
    DocumentSaveIn,
    ProcessedOut,
    ProcessTextIn,
)
from ..security import get_current_user
from ..services import document_processing as dp
from ..services import jobs
from ..services import llm
from ..services import settings_service as svc
from ..services.extract import ExtractionError

router = APIRouter(prefix="/api/documents", tags=["documents"])
logger = get_logger(__name__)
app_settings = get_settings()

LLM_KEYS = (
    "llm_provider",
    "llm_model",
    "llm_base_url",
    "llm_max_tokens",
    "llm_temperature",
    "llm_timeout",
    "llm_api_key",
    "sorin_cli_path",
    "codex_cli_path",
)


def _llm_overrides(db: Session) -> dict:
    resolved = svc.get_all_resolved(db)
    return {k: resolved.get(k, "") for k in LLM_KEYS if resolved.get(k)}


# --- Processing (preview, not yet saved) ----------------------------------
@router.post("/process-file", response_model=ProcessedOut)
async def process_file(
    file: UploadFile = File(...),
    protection_mode: str = Form("mask"),
    optimization_mode: str = Form("balanced"),
    max_tokens: int | None = Form(None),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Extract -> markdown -> protect -> optimize for an uploaded file."""
    app_settings.ensure_dirs()
    safe_name = Path(file.filename or "upload").name
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    dest = app_settings.uploads_dir / stored_name
    try:
        content = await file.read()
        dest.write_bytes(content)
    except OSError as e:
        raise HTTPException(500, f"Could not save upload: {e}")

    try:
        result = dp.process(
            file_path=dest,
            title=safe_name,
            protection_mode=protection_mode,
            optimization_mode=optimization_mode,
            max_tokens=max_tokens,
            db=db,
            token_scope="global",
        )
    except ExtractionError as e:
        raise HTTPException(422, str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("Processing failed for %s", safe_name)
        raise HTTPException(500, f"Processing failed: {e}")

    out = result.to_dict()
    out.update(
        source_type="file",
        source_ref=safe_name,
        stored_path=stored_name,
        mime=file.content_type or "",
    )
    return out


@router.post("/process-text", response_model=ProcessedOut)
def process_text(
    payload: ProcessTextIn,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Process manual text, markdown, JSON/CSV/HTML, or a fetched URL."""
    source_type = "text"
    source_ref = ""
    raw = payload.text or ""
    kind = payload.kind

    if payload.url:
        source_type = "url"
        source_ref = payload.url
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(payload.url, headers={"User-Agent": "SOC-Workbench/1.0"})
                resp.raise_for_status()
                raw = resp.text
                kind = "html"
        except httpx.HTTPError as e:
            raise HTTPException(422, f"Could not fetch URL: {e}")

    if not raw.strip():
        raise HTTPException(422, "No text provided.")

    try:
        result = dp.process(
            raw_text=raw,
            kind=kind,
            title=payload.title,
            protection_mode=payload.protection_mode,
            optimization_mode=payload.optimization_mode,
            max_tokens=payload.max_tokens,
            db=db,
            token_scope="global",
        )
    except ExtractionError as e:
        raise HTTPException(422, str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("Text processing failed")
        raise HTTPException(500, f"Processing failed: {e}")

    out = result.to_dict()
    out.update(source_type=source_type, source_ref=source_ref)
    return out


# --- Persist / list / edit ------------------------------------------------
@router.post("", response_model=DocumentOut)
def save_document(
    payload: DocumentSaveIn,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    doc = Document(**payload.model_dump())
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("", response_model=list[DocumentListItem])
def list_documents(
    q: str = "",
    limit: int = 100,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    query = db.query(Document)
    if q:
        like = f"%{q}%"
        query = query.filter(Document.title.ilike(like) | Document.summary.ilike(like))
    return query.order_by(Document.created_at.desc()).limit(limit).all()


@router.get("/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: int, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@router.put("/{doc_id}", response_model=DocumentOut)
def update_document(
    doc_id: int,
    payload: DocumentSaveIn,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    for k, v in payload.model_dump().items():
        setattr(doc, k, v)
    db.commit()
    db.refresh(doc)
    return doc


@router.delete("/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    # Remove the stored upload file too, if any.
    if doc.stored_path:
        f = app_settings.uploads_dir / doc.stored_path
        if f.exists():
            try:
                f.unlink()
            except OSError:
                logger.warning("Could not delete upload file %s", f)
    db.delete(doc)
    db.commit()
    return {"ok": True}


# --- LLM analysis (background job) ----------------------------------------
@router.post("/{doc_id}/analyze")
def analyze_document(
    doc_id: int,
    payload: AnalyzeIn,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Send the PROTECTED/OPTIMIZED content to the LLM as a background job.

    Only the protected version is ever sent to the provider.
    """
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")

    content = doc.optimized_markdown if payload.use_version == "optimized" else doc.protected_markdown
    content = content or doc.protected_markdown or doc.markdown
    if not content.strip():
        raise HTTPException(422, "Document has no content to analyze.")

    overrides = _llm_overrides(db)
    if payload.model:
        overrides["llm_model"] = payload.model
    if payload.max_tokens:
        overrides["llm_max_tokens"] = str(payload.max_tokens)
    if not llm.config_from_settings(overrides).has_credentials:
        raise HTTPException(
            400,
            "No LLM credentials configured. Set an API key in Settings → LLM, or "
            "select the 'sorin_cli' provider to use the local Sorin Code agent.",
        )

    system = payload.system_prompt or "You are a senior SOC analyst assistant. Be precise and cite only what is in the content."
    user = f"{payload.instruction}\n\n---\n\n{content}"

    def worker() -> str:
        cfg = llm.config_from_settings(overrides)
        res = llm.complete(system, user, cfg)
        wdb = jobs.SessionLocal()
        try:
            d = wdb.get(Document, doc_id)
            if d:
                d.sorin_analysis = res.text
                wdb.add(
                    Analysis(
                        kind="llm",
                        title=f"Analysis: {d.title}",
                        query=payload.instruction,
                        input_summary=d.summary,
                        result=res.text,
                        model=res.model,
                        token_estimate=res.input_tokens + res.output_tokens,
                    )
                )
                wdb.commit()
            return f"{res.output_tokens} output tokens via {res.model}"
        finally:
            wdb.close()

    job_id = jobs.submit(
        "llm", f"Analyze document: {doc.title}", worker, ref_type="document", ref_id=doc_id
    )
    return {"job_id": job_id, "status": "pending"}


# --- Save to knowledge base -----------------------------------------------
@router.post("/{doc_id}/to-knowledge")
def document_to_knowledge(
    doc_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    body = doc.sorin_analysis or doc.protected_markdown or doc.markdown
    item = KnowledgeItem(
        title=doc.title,
        item_type="note",
        content=body,
        summary=doc.summary,
        source=doc.source_ref or doc.source_type,
        tags=(doc.entities or {}).get("keywords", [])[:8],
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"knowledge_id": item.id}
