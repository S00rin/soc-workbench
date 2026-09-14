"""In-app + channel notification helper used by anomaly and brief jobs."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..logging_config import get_logger
from ..models.entities import Notification
from . import notifier
from .settings_service import get_all_resolved

logger = get_logger(__name__)


def deliver(
    db: Session,
    *,
    subject: str,
    body: str,
    ref_type: str = "",
    ref_id: int | None = None,
    channel: str = "inapp",
    recipients: str = "",
    settings: dict[str, str] | None = None,
) -> Notification:
    """Persist a notification and optionally send it on a configured channel."""
    cfg = settings if settings is not None else get_all_resolved(db)
    channel = (channel or "inapp").strip().lower() or "inapp"
    recipients = recipients or ""
    if channel == "telegram" and not recipients:
        recipients = cfg.get("telegram_chat_id") or ""
    record = Notification(
        channel=channel, subject=subject, body=body, recipients=recipients,
        status="pending", ref_type=ref_type, ref_id=ref_id,
    )
    db.add(record)
    db.flush()
    try:
        if channel == "email":
            if not recipients:
                raise notifier.NotifyError("No email recipients configured.")
            notifier.send_email(cfg, recipients, subject, body)
        elif channel == "webhook":
            if not recipients:
                raise notifier.NotifyError("No webhook URL configured.")
            notifier.send_webhook(recipients, subject, body, cfg.get("webhook_secret", ""))
        elif channel == "telegram":
            notifier.send_telegram(cfg.get("telegram_token", ""), recipients, f"{subject}\n\n{body}")
        elif channel not in {"inapp", "none", ""}:
            raise notifier.NotifyError(f"Unknown channel: {channel}")
        record.status = "sent" if channel not in {"inapp", "none", ""} else "recorded"
    except notifier.NotifyError as exc:
        record.status = "failed" if channel not in {"inapp", "none", ""} else "recorded"
        record.error = str(exc)[:2000]
        logger.warning("Notification delivery failed (%s): %s", channel, exc)
    db.commit()
    db.refresh(record)
    return record
