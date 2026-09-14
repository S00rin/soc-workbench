"""IoC repository (Module 9, core CRUD + extraction + dedupe + lifecycle)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.entities import IoC
from ..models.ops import IoCSighting
from ..schemas import IoCBulkIn, IoCIn, IoCOut
from ..security import get_current_user
from ..services import ioc_lifecycle
from ..services.entities import extract_iocs

router = APIRouter(prefix="/api/iocs", tags=["iocs"])

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
    status: str = "",
    watchlist: bool | None = None,
    limit: int = 500,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    query = db.query(IoC)
    if q:
        query = query.filter(IoC.value.ilike(f"%{q}%"))
    if ioc_type:
        query = query.filter(IoC.ioc_type == ioc_type)
    if status:
        query = query.filter(IoC.status == status)
    if watchlist is True:
        query = query.filter(IoC.watchlist.is_(True))
    return query.order_by(IoC.created_at.desc()).limit(limit).all()


@router.get("/lifecycle")
def lifecycle_summary(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    from sqlalchemy import func

    total = db.query(func.count()).select_from(IoC).scalar() or 0
    by_status = dict(db.query(IoC.status, func.count()).group_by(IoC.status).all())
    watchlist = db.query(func.count()).select_from(IoC).filter(IoC.watchlist.is_(True)).scalar() or 0
    avg_score = db.query(func.avg(IoC.score)).scalar()
    return {
        "total": total,
        "by_status": by_status,
        "watchlist": watchlist,
        "avg_score": round(float(avg_score), 1) if avg_score is not None else None,
    }


@router.post("/lifecycle/run")
def run_lifecycle(hunt: bool = False, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    return ioc_lifecycle.run_lifecycle(db, hunt=hunt)


@router.post("/lifecycle/retrohunt")
def retrohunt(db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    return ioc_lifecycle.retro_hunt(db)


@router.get("/export/watchlist")
def export_watchlist(
    fmt: str = "csv",
    scope: str = "watchlist",
    db: Session = Depends(get_db),
    _: str = Depends(get_current_user),
):
    if fmt not in {"csv", "stix"}:
        raise HTTPException(400, "fmt must be csv or stix")
    if scope not in {"watchlist", "active"}:
        raise HTTPException(400, "scope must be watchlist or active")
    rows = ioc_lifecycle.watchlist_query(db, scope=scope)
    if fmt == "stix":
        bundle = ioc_lifecycle.export_stix(rows)
        return JSONResponse(bundle, headers={"Content-Disposition": "attachment; filename=watchlist.stix.json"})
    csv_body = ioc_lifecycle.export_csv(rows)
    return PlainTextResponse(
        csv_body, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=watchlist.csv"},
    )


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


class IoCPatch(BaseModel):
    watchlist: bool | None = None
    false_positive: bool | None = None
    status: str | None = None
    notes: str | None = None


@router.patch("/{ioc_id}", response_model=IoCOut)
def patch_ioc(ioc_id: int, payload: IoCPatch, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    ioc = db.get(IoC, ioc_id)
    if not ioc:
        raise HTTPException(404, "IoC not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(ioc, key, value)
    if ioc.watchlist and ioc.status not in {"expired", "retired"}:
        ioc.status = "watchlist"
    db.commit()
    db.refresh(ioc)
    return ioc


@router.get("/{ioc_id}/sightings")
def sightings(ioc_id: int, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    if not db.get(IoC, ioc_id):
        raise HTTPException(404, "IoC not found")
    rows = db.query(IoCSighting).filter(IoCSighting.ioc_id == ioc_id).order_by(IoCSighting.id.desc()).limit(50).all()
    return [ioc_lifecycle.serialize_sighting(row) for row in rows]


@router.delete("/{ioc_id}")
def delete_ioc(ioc_id: int, db: Session = Depends(get_db), _: str = Depends(get_current_user)):
    ioc = db.get(IoC, ioc_id)
    if not ioc:
        raise HTTPException(404, "IoC not found")
    db.delete(ioc)
    db.commit()
    return {"ok": True}
