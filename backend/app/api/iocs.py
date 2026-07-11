"""IoC repository (Module 9, core CRUD + extraction + dedupe)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.entities import IoC
from ..schemas import IoCBulkIn, IoCIn, IoCOut
from ..security import get_current_user
from ..services.entities import extract_iocs

router = APIRouter(prefix="/api/iocs", tags=["iocs"])

# Map the extractor's buckets to IoC types.
_BUCKET_TYPE = {
    "ips": "ipv4",
    "urls": "url",
    "domains": "domain",
    "emails": "email",
    "hashes": "hash",
}


@router.get("", response_model=list[IoCOut])
def list_iocs(
    q: str = "",
    ioc_type: str = "",
    limit: int = 500,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    query = db.query(IoC)
    if q:
        query = query.filter(IoC.value.ilike(f"%{q}%"))
    if ioc_type:
        query = query.filter(IoC.ioc_type == ioc_type)
    return query.order_by(IoC.created_at.desc()).limit(limit).all()


@router.post("", response_model=IoCOut)
def create_ioc(payload: IoCIn, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    existing = db.query(IoC).filter(IoC.value == payload.value).first()
    if existing:
        raise HTTPException(409, "IoC already exists")
    ioc = IoC(**payload.model_dump())
    db.add(ioc)
    db.commit()
    db.refresh(ioc)
    return ioc


@router.post("/extract", response_model=list[IoCOut])
def extract_and_store(
    payload: IoCBulkIn,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Extract IoCs from free text and store the new (deduplicated) ones."""
    buckets = extract_iocs(payload.text)
    existing = {v for (v,) in db.query(IoC.value).all()}
    created: list[IoC] = []
    for bucket, ioc_type in _BUCKET_TYPE.items():
        for value in buckets.get(bucket, []):
            if value in existing:
                continue
            existing.add(value)
            ioc = IoC(value=value, ioc_type=ioc_type, source=payload.source or "extraction")
            db.add(ioc)
            created.append(ioc)
    db.commit()
    for ioc in created:
        db.refresh(ioc)
    return created


@router.delete("/{ioc_id}")
def delete_ioc(ioc_id: int, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    ioc = db.get(IoC, ioc_id)
    if not ioc:
        raise HTTPException(404, "IoC not found")
    db.delete(ioc)
    db.commit()
    return {"ok": True}
