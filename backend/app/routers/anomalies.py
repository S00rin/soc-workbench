"""Silent-sensor and feed-anomaly alerts."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..security import AuthContext, get_auth_context
from ..services import anomaly_detection

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


@router.get("")
def list_anomalies(status: str = "open", db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    return anomaly_detection.list_anomalies(db, context.tenant_id, status=status)


@router.get("/summary")
def summary(db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    return anomaly_detection.summary(db, context.tenant_id)


@router.post("/run")
def run(db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    return anomaly_detection.run_detection(db, context.tenant_id)


@router.post("/{anomaly_id}/ack")
def ack(anomaly_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    try:
        return anomaly_detection.serialize(anomaly_detection.set_status(db, context.tenant_id, anomaly_id, "acked"))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{anomaly_id}/resolve")
def resolve(anomaly_id: int, db: Session = Depends(get_db), context: AuthContext = Depends(get_auth_context)):
    try:
        return anomaly_detection.serialize(anomaly_detection.set_status(db, context.tenant_id, anomaly_id, "resolved"))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
