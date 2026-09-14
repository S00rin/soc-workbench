"""Report generation + export (Module 11)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models.content import IntelItem, KnowledgeItem
from ..models.entities import Analysis, IoC, Report
from ..security import get_current_user
from ..services import llm, report_builder
from ..services.settings_service import get_all_resolved

router = APIRouter(prefix="/api/reports", tags=["reports"])
settings = get_settings()

REPORT_TYPES = ["daily_activity", "weekly_project", "monthly_project", "weekly_soc",
                "monthly_soc", "jira_activity", "splunk_health", "threat_digest",
                "incident", "technical", "executive", "adhoc"]


class GenerateRequest(BaseModel):
    title: str
    report_type: str = "weekly_soc"
    language: str = "en"
    detail_level: str = "balanced"
    date_from: str = ""
    date_to: str = ""
    project_id: int | None = None
    customer: str = ""
    data_sources: list[str] = ["knowledge", "intel", "iocs", "analyses"]
    notes: str = ""
    use_llm: bool = True


def _gather_sources(db: Session, req: GenerateRequest) -> dict[str, str]:
    sources: dict[str, str] = {}
    if "knowledge" in req.data_sources:
        items = db.query(KnowledgeItem).order_by(desc(KnowledgeItem.updated_at)).limit(20).all()
        sources["Knowledge Base"] = "\n".join(f"- {i.title}: {i.summary}" for i in items)
    if "intel" in req.data_sources:
        items = db.query(IntelItem).order_by(desc(IntelItem.created_at)).limit(20).all()
        sources["Internet Intelligence"] = "\n".join(
            f"- [{i.category}] {i.title} ({i.source})" for i in items)
    if "iocs" in req.data_sources:
        items = db.query(IoC).order_by(desc(IoC.created_at)).limit(30).all()
        sources["IoCs"] = "\n".join(f"- {i.ioc_type}: {i.value} ({i.severity})" for i in items)
    if "analyses" in req.data_sources:
        items = db.query(Analysis).order_by(desc(Analysis.created_at)).limit(15).all()
        sources["Analyses"] = "\n\n".join(f"### {i.title}\n{i.result[:1500]}" for i in items)
    if req.notes:
        sources["Manual Notes"] = req.notes
    return sources


@router.get("/types")
def types(user: str = Depends(get_current_user)):
    return REPORT_TYPES


@router.post("/generate")
def generate(req: GenerateRequest, db: Session = Depends(get_db),
             user: str = Depends(get_current_user)):
    sources = _gather_sources(db, req)
    skeleton = report_builder.build_skeleton(
        req.title, req.report_type, req.date_from or "-", req.date_to or "-",
        sources, req.language)
    content = skeleton
    cfg = llm.config_from_settings(get_all_resolved(db))
    if req.use_llm and cfg.has_credentials:
        instruction = report_builder.build_llm_instruction(
            req.title, req.report_type, req.language, req.detail_level)
        source_text = "\n\n".join(f"## {k}\n{v}" for k, v in sources.items() if v.strip())
        try:
            content = llm.complete(instruction, source_text or "No source data available.", cfg).text
        except llm.LLMError as e:
            content = skeleton + f"\n\n> _LLM generation failed: {e}. Skeleton shown._"
    report = Report(title=req.title, report_type=req.report_type, language=req.language,
                    detail_level=req.detail_level, project_id=req.project_id,
                    customer=req.customer, date_from=req.date_from, date_to=req.date_to,
                    data_sources=req.data_sources, content=content)
    db.add(report)
    db.commit()
    db.refresh(report)
    return {"id": report.id, "content": content}


@router.get("")
def list_reports(db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    rows = db.query(Report).order_by(desc(Report.created_at)).limit(100).all()
    return [{"id": r.id, "title": r.title, "report_type": r.report_type,
             "language": r.language, "status": r.status, "created_at": r.created_at}
            for r in rows]


@router.get("/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db),
               user: str = Depends(get_current_user)):
    row = db.get(Report, report_id)
    if not row:
        raise HTTPException(404, "Report not found")
    return {c.name: getattr(row, c.name) for c in Report.__table__.columns}


class UpdateReport(BaseModel):
    content: str


@router.put("/{report_id}")
def update_report(report_id: int, req: UpdateReport, db: Session = Depends(get_db),
                  user: str = Depends(get_current_user)):
    row = db.get(Report, report_id)
    if not row:
        raise HTTPException(404, "Report not found")
    versions = list(row.versions or [])
    versions.append({"ts": datetime.now(timezone.utc).isoformat(), "content": row.content})
    row.versions = versions
    row.content = req.content
    db.commit()
    return {"ok": True, "versions": len(versions)}


@router.get("/{report_id}/export")
def export_report(report_id: int, fmt: str = "md", db: Session = Depends(get_db),
                  user: str = Depends(get_current_user)):
    row = db.get(Report, report_id)
    if not row:
        raise HTTPException(404, "Report not found")
    name = f"report-{report_id}"
    try:
        if fmt == "md":
            path = report_builder.export_markdown(row.content, settings.reports_dir, name)
        elif fmt == "html":
            path = report_builder.export_html(row.content, settings.reports_dir, name, row.title)
        elif fmt == "docx":
            path = report_builder.export_docx(row.content, settings.reports_dir, name)
        elif fmt == "pdf":
            path = report_builder.export_pdf(row.content, settings.reports_dir, name, row.title, row.language or "en")
        else:
            raise HTTPException(400, "Unsupported format")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Export failed: {e}")
    return FileResponse(str(path), filename=path.name)


@router.delete("/{report_id}")
def delete_report(report_id: int, db: Session = Depends(get_db),
                  user: str = Depends(get_current_user)):
    row = db.get(Report, report_id)
    if not row:
        raise HTTPException(404, "Report not found")
    db.delete(row)
    db.commit()
    return {"ok": True}
