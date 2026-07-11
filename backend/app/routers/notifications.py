"""Notification center (Module 12)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.entities import Notification
from ..security import get_current_user
from ..services import notifier
from ..services.settings_service import get_all_resolved

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

TEMPLATES = {
    "critical_alert": "🚨 Critical alert: {title}\n\n{body}",
    "weekly_report": "Weekly report: {title}\n\n{body}",
    "monthly_report": "Monthly report: {title}\n\n{body}",
    "incident": "Incident notification: {title}\n\n{body}",
    "project_risk": "Project risk: {title}\n\n{body}",
    "customer_action": "Customer action required: {title}\n\n{body}",
    "recommendation": "Technical recommendation: {title}\n\n{body}",
}


class SendRequest(BaseModel):
    channel: str  # email | webhook | telegram
    subject: str = ""
    body: str
    recipients: str = ""  # email addresses / webhook url
    template: str = ""


@router.get("/templates")
def templates(user: str = Depends(get_current_user)):
    return list(TEMPLATES.keys())


@router.post("/send")
def send(req: SendRequest, db: Session = Depends(get_db),
         user: str = Depends(get_current_user)):
    body = req.body
    if req.template and req.template in TEMPLATES:
        body = TEMPLATES[req.template].format(title=req.subject, body=req.body)

    cfg = get_all_resolved(db)
    record = Notification(channel=req.channel, subject=req.subject, body=body,
                          recipients=req.recipients, status="pending")
    db.add(record)
    db.commit()
    db.refresh(record)
    try:
        if req.channel == "email":
            notifier.send_email(cfg, req.recipients, req.subject or "Notification", body)
        elif req.channel == "webhook":
            notifier.send_webhook(req.recipients, req.subject, body,
                                  cfg.get("webhook_secret", ""))
        elif req.channel == "telegram":
            notifier.send_telegram(cfg.get("telegram_token", ""),
                                   req.recipients or cfg.get("telegram_chat_id", ""), body)
        else:
            raise notifier.NotifyError(f"Unknown channel: {req.channel}")
        record.status = "sent"
    except notifier.NotifyError as e:
        record.status = "failed"
        record.error = str(e)
        db.commit()
        raise HTTPException(400, str(e))
    db.commit()
    return {"id": record.id, "status": record.status}


@router.get("")
def history(db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    rows = db.query(Notification).order_by(desc(Notification.created_at)).limit(100).all()
    return [{"id": r.id, "channel": r.channel, "subject": r.subject,
             "recipients": r.recipients, "status": r.status, "error": r.error,
             "created_at": r.created_at} for r in rows]
