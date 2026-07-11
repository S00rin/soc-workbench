"""Notification delivery (Module 12): email (SMTP), webhook, Telegram.

Credentials are read from settings (decrypted) and never logged.
"""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from ..logging_config import get_logger

logger = get_logger(__name__)


class NotifyError(Exception):
    pass


def send_email(cfg: dict, to: str, subject: str, body_markdown: str) -> None:
    host = cfg.get("smtp_host")
    if not host:
        raise NotifyError("SMTP host not configured.")
    port = int(cfg.get("smtp_port") or 587)
    username = cfg.get("smtp_username", "")
    password = cfg.get("smtp_password", "")
    sender = cfg.get("smtp_from") or username
    use_tls = str(cfg.get("smtp_tls", "true")).lower() == "true"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.attach(MIMEText(body_markdown, "plain", "utf-8"))

    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            if use_tls:
                server.starttls()
            if username:
                server.login(username, password)
            server.sendmail(sender, [r.strip() for r in to.split(",")], msg.as_string())
        logger.info("Email sent to %s", to)
    except (smtplib.SMTPException, OSError) as e:
        raise NotifyError(f"Email delivery failed: {e}") from e


def send_webhook(url: str, subject: str, body: str, secret: str = "") -> None:
    if not url:
        raise NotifyError("Webhook URL not provided.")
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Webhook-Secret"] = secret
    try:
        with httpx.Client(timeout=20) as c:
            r = c.post(url, json={"subject": subject, "body": body}, headers=headers)
            r.raise_for_status()
        logger.info("Webhook delivered to %s", url.split("/")[2] if "//" in url else url)
    except httpx.HTTPError as e:
        raise NotifyError(f"Webhook delivery failed: {e}") from e


def send_telegram(token: str, chat_id: str, text: str) -> None:
    if not token or not chat_id:
        raise NotifyError("Telegram token/chat id not configured.")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=20) as c:
            r = c.post(url, json={"chat_id": chat_id, "text": text[:4096]})
            r.raise_for_status()
        logger.info("Telegram message sent to chat %s", chat_id)
    except httpx.HTTPError as e:
        raise NotifyError(f"Telegram delivery failed: {e}") from e
