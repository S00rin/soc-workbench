"""Project price analyzer API: contract ingestion, effort estimation, cost
calculation, WBS/Gantt scheduling, RACI matrix and export (Module 17)."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..logging_config import get_logger
from ..models.entities import Project, Report
from ..models.price_analyzer import DEFAULT_COEFFICIENTS, Contract, ContractSection, RACIEntry, WBSItem
from ..security import get_current_user
from ..services import extract, llm, price_analyzer as pa
from ..services.extract import ExtractionError
from ..services.settings_service import get_all_resolved

router = APIRouter(prefix="/api/price-analyzer", tags=["price-analyzer"])
logger = get_logger(__name__)
app_settings = get_settings()

LLM_KEYS = (
    "llm_provider", "llm_model", "llm_base_url", "llm_max_tokens",
    "llm_temperature", "llm_timeout", "llm_api_key", "claude_cli_path",
)


def _llm_overrides(db: Session) -> dict:
    resolved = get_all_resolved(db)
    return {k: resolved.get(k, "") for k in LLM_KEYS if resolved.get(k)}


def _get_contract(db: Session, contract_id: int) -> Contract:
    row = db.get(Contract, contract_id)
    if not row:
        raise HTTPException(404, "Contract not found")
    return row


def _contract_out(row: Contract) -> dict:
    return {
        "id": row.id, "title": row.title, "customer": row.customer, "project_id": row.project_id,
        "language": row.language, "status": row.status, "source_type": row.source_type,
        "source_ref": row.source_ref, "coefficients": row.coefficients, "schedule_start": row.schedule_start,
        "summary": row.summary, "notes": row.notes, "created_by": row.created_by,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }


def _section_out(row: ContractSection) -> dict:
    return {
        "id": row.id, "contract_id": row.contract_id, "order_index": row.order_index, "title": row.title,
        "category": row.category, "role": row.role, "excerpt": row.excerpt,
        "estimated_hours": row.estimated_hours, "adjusted_hours": row.adjusted_hours,
        "hourly_rate_override": row.hourly_rate_override, "notes": row.notes,
    }


def _wbs_out(row: WBSItem) -> dict:
    return {
        "id": row.id, "contract_id": row.contract_id, "parent_id": row.parent_id, "section_id": row.section_id,
        "level": row.level, "code": row.code, "title": row.title, "order_index": row.order_index,
        "start_date": row.start_date, "end_date": row.end_date, "duration_days": row.duration_days,
        "percent_complete": row.percent_complete, "assignee": row.assignee,
    }


def _raci_out(row: RACIEntry) -> dict:
    return {"id": row.id, "wbs_item_id": row.wbs_item_id, "participant": row.participant, "raci": row.raci}


# --- Contracts ---------------------------------------------------------------

class ContractTextIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    customer: str = Field(default="", max_length=200)
    language: str = Field(default="fa", pattern="^(en|fa)$")
    project_id: int | None = None
    text: str = Field(min_length=1)


class ContractUpdateIn(BaseModel):
    title: str | None = Field(default=None, max_length=240)
    customer: str | None = Field(default=None, max_length=200)
    language: str | None = Field(default=None, pattern="^(en|fa)$")
    project_id: int | None = None
    status: str | None = None
    coefficients: dict | None = None
    schedule_start: str | None = None
    notes: str | None = None


@router.post("/contracts")
def create_contract_from_text(payload: ContractTextIn, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    row = Contract(
        title=payload.title, customer=payload.customer, language=payload.language,
        project_id=payload.project_id, source_type="text", source_text=payload.text,
        created_by=user,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _contract_out(row)


@router.post("/contracts/upload")
async def upload_contract(
    file: UploadFile = File(...), title: str = Form(""), customer: str = Form(""),
    language: str = Form("fa"), project_id: int | None = Form(None),
    db: Session = Depends(get_db), user: str = Depends(get_current_user),
):
    app_settings.ensure_dirs()
    safe_name = Path(file.filename or "contract").name
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    dest = app_settings.uploads_dir / stored_name
    try:
        content = await file.read()
        dest.write_bytes(content)
        text = extract.extract_file(dest)
    except ExtractionError as e:
        raise HTTPException(422, str(e))
    except OSError as e:
        raise HTTPException(500, f"Could not save upload: {e}")

    row = Contract(
        title=title or safe_name, customer=customer, language=language, project_id=project_id,
        source_type="file", source_ref=safe_name, stored_path=stored_name, source_text=text,
        created_by=user,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _contract_out(row)


@router.get("/contracts")
def list_contracts(project_id: int | None = None, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    query = db.query(Contract)
    if project_id is not None:
        query = query.filter(Contract.project_id == project_id)
    rows = query.order_by(Contract.updated_at.desc()).limit(200).all()
    return [_contract_out(r) for r in rows]


@router.get("/contracts/{contract_id}")
def get_contract(contract_id: int, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    contract = _get_contract(db, contract_id)
    sections = db.query(ContractSection).filter(ContractSection.contract_id == contract_id).order_by(ContractSection.order_index).all()
    wbs = db.query(WBSItem).filter(WBSItem.contract_id == contract_id).order_by(WBSItem.order_index).all()
    raci = db.query(RACIEntry).filter(RACIEntry.contract_id == contract_id).all()
    cost = pa.compute_costs(sections, contract.coefficients or DEFAULT_COEFFICIENTS)
    return {
        "contract": _contract_out(contract),
        "sections": [_section_out(s) for s in sections],
        "wbs": [_wbs_out(w) for w in wbs],
        "raci": [_raci_out(r) for r in raci],
        "cost": cost,
    }


@router.put("/contracts/{contract_id}")
def update_contract(contract_id: int, payload: ContractUpdateIn, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    contract = _get_contract(db, contract_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(contract, key, value)
    db.commit()
    db.refresh(contract)
    return _contract_out(contract)


@router.delete("/contracts/{contract_id}")
def delete_contract(contract_id: int, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    contract = _get_contract(db, contract_id)
    if contract.stored_path:
        f = app_settings.uploads_dir / contract.stored_path
        if f.exists():
            try:
                f.unlink()
            except OSError:
                logger.warning("Could not delete contract upload %s", f)
    db.delete(contract)
    db.commit()
    return {"ok": True}


# --- Analysis (section split + estimate) -------------------------------------

@router.post("/contracts/{contract_id}/analyze")
def analyze_contract(contract_id: int, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    contract = _get_contract(db, contract_id)
    if not contract.source_text.strip():
        raise HTTPException(422, "Contract has no extracted text to analyze.")
    coefficients = contract.coefficients or DEFAULT_COEFFICIENTS

    raw_sections: list[dict] | None = None
    method = "heuristic"
    cfg = llm.config_from_settings(_llm_overrides(db))
    if cfg.has_credentials:
        try:
            raw_sections = pa.split_sections_with_llm(contract.source_text, contract.language, coefficients, cfg)
            method = "ai"
        except (llm.LLMError, pa.AnalysisError) as e:
            logger.warning("LLM contract split failed, falling back to heuristic: %s", e)
    if raw_sections is None:
        try:
            raw_sections = pa.split_sections_heuristic(contract.source_text, coefficients, contract.language)
        except pa.AnalysisError as e:
            raise HTTPException(422, str(e))

    db.query(ContractSection).filter(ContractSection.contract_id == contract_id).delete()
    db.flush()
    persisted = []
    for item in raw_sections:
        row = ContractSection(
            contract_id=contract_id, order_index=item["order_index"], title=item["title"],
            category=item["category"], role=item["role"], excerpt=item["excerpt"],
            estimated_hours=item["estimated_hours"], adjusted_hours=item["estimated_hours"],
        )
        db.add(row)
        persisted.append(row)
    contract.status = "analyzed"
    db.commit()
    for row in persisted:
        db.refresh(row)
    return {"method": method, "sections": [_section_out(row) for row in persisted]}


# --- Sections -----------------------------------------------------------------

class SectionIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    category: str = "other"
    role: str = "unassigned"
    excerpt: str = ""
    estimated_hours: float = 0
    adjusted_hours: float = 0
    hourly_rate_override: float | None = None
    notes: str = ""


class SectionUpdateIn(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    category: str | None = None
    role: str | None = None
    excerpt: str | None = None
    adjusted_hours: float | None = None
    hourly_rate_override: float | None = None
    notes: str | None = None


@router.get("/contracts/{contract_id}/sections")
def list_sections(contract_id: int, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    _get_contract(db, contract_id)
    rows = db.query(ContractSection).filter(ContractSection.contract_id == contract_id).order_by(ContractSection.order_index).all()
    return [_section_out(r) for r in rows]


@router.post("/contracts/{contract_id}/sections")
def add_section(contract_id: int, payload: SectionIn, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    contract = _get_contract(db, contract_id)
    max_order = db.query(ContractSection).filter(ContractSection.contract_id == contract_id).count()
    row = ContractSection(contract_id=contract_id, order_index=max_order, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _section_out(row)


@router.put("/contracts/{contract_id}/sections/{section_id}")
def update_section(contract_id: int, section_id: int, payload: SectionUpdateIn, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    row = db.query(ContractSection).filter(ContractSection.id == section_id, ContractSection.contract_id == contract_id).first()
    if not row:
        raise HTTPException(404, "Section not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _section_out(row)


@router.delete("/contracts/{contract_id}/sections/{section_id}")
def delete_section(contract_id: int, section_id: int, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    row = db.query(ContractSection).filter(ContractSection.id == section_id, ContractSection.contract_id == contract_id).first()
    if not row:
        raise HTTPException(404, "Section not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/contracts/{contract_id}/costs")
def get_costs(contract_id: int, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    contract = _get_contract(db, contract_id)
    sections = db.query(ContractSection).filter(ContractSection.contract_id == contract_id).order_by(ContractSection.order_index).all()
    return pa.compute_costs(sections, contract.coefficients or DEFAULT_COEFFICIENTS)


# --- WBS / Gantt ---------------------------------------------------------------

class WBSGenerateIn(BaseModel):
    schedule_start: str | None = None


class WBSUpdateIn(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    start_date: str | None = None
    end_date: str | None = None
    percent_complete: int | None = Field(default=None, ge=0, le=100)
    assignee: str | None = None


def _persist_wbs(db: Session, contract: Contract, sections: list[ContractSection]) -> list[WBSItem]:
    db.query(RACIEntry).filter(RACIEntry.contract_id == contract.id).delete()
    db.query(WBSItem).filter(WBSItem.contract_id == contract.id).delete()
    db.flush()

    raw_items = pa.generate_wbs(contract.title, sections, contract.language)
    code_to_id: dict[str, int] = {}
    persisted: list[WBSItem] = []
    for item in raw_items:
        parent_code = item["_parent_code"]
        row = WBSItem(
            contract_id=contract.id, parent_id=code_to_id.get(parent_code) if parent_code else None,
            section_id=item["section_id"], level=item["level"], code=item["code"],
            title=item["title"], order_index=item["order_index"],
        )
        db.add(row)
        db.flush()
        code_to_id[item["code"]] = row.id
        persisted.append(row)

    coefficients = contract.coefficients or DEFAULT_COEFFICIENTS
    hours_per_day = float(coefficients.get("hours_per_day") or 8.0)
    hours_by_section = {s.id: s.adjusted_hours for s in sections}
    wbs_dicts = [
        {"id": r.id, "parent_id": r.parent_id, "level": r.level, "order_index": r.order_index, "section_id": r.section_id}
        for r in persisted
    ]
    schedule = pa.schedule_wbs(wbs_dicts, hours_by_section, hours_per_day, contract.schedule_start)
    for row in persisted:
        entry = schedule.get(row.id)
        if entry:
            row.start_date = entry["start"].isoformat()
            row.end_date = entry["end"].isoformat()
            row.duration_days = entry["duration"]

    for entry in pa.suggest_raci([{"id": r.id, "level": r.level} for r in persisted]):
        db.add(RACIEntry(contract_id=contract.id, wbs_item_id=entry["wbs_item_id"], participant=entry["participant"], raci=entry["raci"]))
    db.commit()
    return persisted


@router.post("/contracts/{contract_id}/wbs/generate")
def generate_wbs(contract_id: int, payload: WBSGenerateIn, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    contract = _get_contract(db, contract_id)
    sections = db.query(ContractSection).filter(ContractSection.contract_id == contract_id).order_by(ContractSection.order_index).all()
    if not sections:
        raise HTTPException(422, "Analyze the contract into sections before generating a WBS.")
    if payload.schedule_start:
        contract.schedule_start = payload.schedule_start
    persisted = _persist_wbs(db, contract, sections)
    raci = db.query(RACIEntry).filter(RACIEntry.contract_id == contract_id).all()
    return {"wbs": [_wbs_out(r) for r in persisted], "raci": [_raci_out(r) for r in raci]}


@router.get("/contracts/{contract_id}/wbs")
def list_wbs(contract_id: int, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    _get_contract(db, contract_id)
    rows = db.query(WBSItem).filter(WBSItem.contract_id == contract_id).order_by(WBSItem.order_index).all()
    return [_wbs_out(r) for r in rows]


@router.put("/contracts/{contract_id}/wbs/{item_id}")
def update_wbs_item(contract_id: int, item_id: int, payload: WBSUpdateIn, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    row = db.query(WBSItem).filter(WBSItem.id == item_id, WBSItem.contract_id == contract_id).first()
    if not row:
        raise HTTPException(404, "WBS item not found")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(row, key, value)
    if ("start_date" in changes or "end_date" in changes) and row.start_date and row.end_date:
        start, end = pa.parse_date(row.start_date), pa.parse_date(row.end_date)
        row.duration_days = float(max(0, (end - start).days + 1))
    db.commit()
    db.refresh(row)
    return _wbs_out(row)


# --- RACI matrix ----------------------------------------------------------------

class RACIEntryIn(BaseModel):
    wbs_item_id: int
    participant: str = Field(min_length=1, max_length=160)
    raci: str = Field(pattern="^[RACI]$")


class RACIReplaceIn(BaseModel):
    entries: list[RACIEntryIn]


@router.get("/contracts/{contract_id}/raci")
def list_raci(contract_id: int, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    _get_contract(db, contract_id)
    rows = db.query(RACIEntry).filter(RACIEntry.contract_id == contract_id).all()
    return [_raci_out(r) for r in rows]


@router.put("/contracts/{contract_id}/raci")
def replace_raci(contract_id: int, payload: RACIReplaceIn, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    _get_contract(db, contract_id)
    valid_ids = {row.id for row in db.query(WBSItem.id).filter(WBSItem.contract_id == contract_id).all()}
    for entry in payload.entries:
        if entry.wbs_item_id not in valid_ids:
            raise HTTPException(422, f"WBS item {entry.wbs_item_id} does not belong to this contract.")
    db.query(RACIEntry).filter(RACIEntry.contract_id == contract_id).delete()
    for entry in payload.entries:
        db.add(RACIEntry(contract_id=contract_id, wbs_item_id=entry.wbs_item_id, participant=entry.participant, raci=entry.raci))
    db.commit()
    rows = db.query(RACIEntry).filter(RACIEntry.contract_id == contract_id).all()
    return [_raci_out(r) for r in rows]


# --- Export ----------------------------------------------------------------------

@router.get("/contracts/{contract_id}/export")
def export_contract(contract_id: int, fmt: str = "pdf", db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    contract = _get_contract(db, contract_id)
    sections = db.query(ContractSection).filter(ContractSection.contract_id == contract_id).order_by(ContractSection.order_index).all()
    wbs = db.query(WBSItem).filter(WBSItem.contract_id == contract_id).order_by(WBSItem.order_index).all()
    raci = db.query(RACIEntry).filter(RACIEntry.contract_id == contract_id).all()
    cost = pa.compute_costs(sections, contract.coefficients or DEFAULT_COEFFICIENTS)
    wbs_dicts = [_wbs_out(r) for r in wbs]
    raci_dicts = [_raci_out(r) for r in raci]
    name = f"price-analysis-{contract_id}"
    try:
        if fmt == "xlsx":
            path = pa.export_excel(contract, cost, wbs_dicts, raci_dicts, app_settings.exports_dir, name)
        elif fmt == "pdf":
            path = pa.export_pdf(contract, cost, wbs_dicts, raci_dicts, app_settings.exports_dir, name)
        else:
            raise HTTPException(400, "Unsupported format (use pdf or xlsx)")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("Price analyzer export failed for contract %s", contract_id)
        raise HTTPException(400, f"Export failed: {e}")
    return FileResponse(str(path), filename=path.name)


# --- Integration with Projects & Reports -----------------------------------------

@router.post("/contracts/{contract_id}/sync-milestones")
def sync_milestones_to_project(contract_id: int, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    contract = _get_contract(db, contract_id)
    if not contract.project_id:
        raise HTTPException(422, "Link this contract to a project first.")
    project = db.get(Project, contract.project_id)
    if not project:
        raise HTTPException(404, "Linked project not found")
    phases = db.query(WBSItem).filter(WBSItem.contract_id == contract_id, WBSItem.level == 2).order_by(WBSItem.order_index).all()
    if not phases:
        raise HTTPException(422, "Generate a WBS for this contract first.")
    milestones = list(project.milestones or [])
    existing_titles = {m.get("title") for m in milestones if isinstance(m, dict)}
    for phase in phases:
        if phase.title in existing_titles:
            continue
        milestones.append({"title": phase.title, "date": phase.end_date, "source": "price_analyzer"})
    project.milestones = milestones
    db.commit()
    return {"ok": True, "milestones": len(milestones)}


@router.post("/contracts/{contract_id}/push-to-report")
def push_to_report(contract_id: int, db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    contract = _get_contract(db, contract_id)
    sections = db.query(ContractSection).filter(ContractSection.contract_id == contract_id).order_by(ContractSection.order_index).all()
    cost = pa.compute_costs(sections, contract.coefficients or DEFAULT_COEFFICIENTS)
    lines = [f"# {contract.title} — Cost Estimate", "", f"*Customer: {contract.customer or '-'} · Currency: {cost['currency']}*", "",
              "## Sections", ""]
    for row in cost["rows"]:
        lines.append(f"- **{row['title']}** ({row['category']}, {row['role']}): {row['hours']}h × {row['rate']} = {row['cost']}")
    lines += ["", "## Totals", "",
              f"- Subtotal: {cost['subtotal']}", f"- Overhead: {cost['overhead_amount']}",
              f"- Contingency: {cost['contingency_amount']}", f"- Discount: -{cost['discount_amount']}",
              f"- Tax: {cost['tax_amount']}", f"- **Total: {cost['total']} {cost['currency']}**"]
    report = Report(
        title=f"Price estimate: {contract.title}", report_type="adhoc", language=contract.language,
        project_id=contract.project_id, customer=contract.customer, content="\n".join(lines),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {"report_id": report.id}
