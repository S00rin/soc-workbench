"""IoC management (Module 9)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.entities import IoC
from ..security import get_current_user
from ..services.entities import extract_iocs

router = APIRouter(prefix="/api/iocs", tags=["iocs"])

IOC_TYPES = ["ipv4", "ipv6", "domain", "url", "hash", "email", "user_agent",
             "filename", "filepath", "process", "registry", "ja3", "ja4", "custom"]


class IoCIn(BaseModel):
    value: str
    ioc_type: str = "custom"
    source: str = ""
    confidence: str = "medium"
    severity: str = "medium"
    tags: list[str] = []
    related_malware: str = ""
    related_actor: str = ""
    related_incident: str = ""
    related_customer: str = ""
    notes: str = ""
    false_positive: bool = False


@router.get("/types")
def types(user: str = Depends(get_current_user)):
    return IOC_TYPES


@router.get("")
def list_iocs(q: str = "", ioc_type: str = "", db: Session = Depends(get_db),
              user: str = Depends(get_current_user)):
    query = db.query(IoC)
    if q:
        query = query.filter(or_(IoC.value.ilike(f"%{q}%"), IoC.notes.ilike(f"%{q}%")))
    if ioc_type:
        query = query.filter(IoC.ioc_type == ioc_type)
    rows = query.order_by(desc(IoC.created_at)).limit(500).all()
    return [{c.name: getattr(r, c.name) for c in IoC.__table__.columns} for r in rows]


@router.post("")
def create_ioc(ioc: IoCIn, db: Session = Depends(get_db),
               user: str = Depends(get_current_user)):
    existing = db.query(IoC).filter(IoC.value == ioc.value,
                                    IoC.ioc_type == ioc.ioc_type).first()
    if existing:
        return {"id": existing.id, "duplicate": True}
    row = IoC(**ioc.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "duplicate": False}


class BulkImport(BaseModel):
    text: str
    source: str = "bulk import"


@router.post("/extract")
def extract_from_text(payload: BulkImport, db: Session = Depends(get_db),
                      user: str = Depends(get_current_user)):
    """Extract IoCs from free text and store new ones (deduplicated)."""
    found = extract_iocs(payload.text)
    type_map = {"ips": "ipv4", "domains": "domain", "urls": "url",
                "emails": "email", "hashes": "hash"}
    added = 0
    for key, ioc_type in type_map.items():
        for value in found.get(key, []):
            exists = db.query(IoC).filter(IoC.value == value, IoC.ioc_type == ioc_type).first()
            if not exists:
                db.add(IoC(value=value, ioc_type=ioc_type, source=payload.source))
                added += 1
    db.commit()
    return {"added": added, "found": {k: len(v) for k, v in found.items()}}


@router.put("/{ioc_id}")
def update_ioc(ioc_id: int, ioc: IoCIn, db: Session = Depends(get_db),
               user: str = Depends(get_current_user)):
    row = db.get(IoC, ioc_id)
    if not row:
        raise HTTPException(404, "IoC not found")
    for field, value in ioc.model_dump().items():
        setattr(row, field, value)
    db.commit()
    return {"ok": True}


@router.delete("/{ioc_id}")
def delete_ioc(ioc_id: int, db: Session = Depends(get_db),
               user: str = Depends(get_current_user)):
    row = db.get(IoC, ioc_id)
    if not row:
        raise HTTPException(404, "IoC not found")
    db.delete(row)
    db.commit()
    return {"ok": True}
