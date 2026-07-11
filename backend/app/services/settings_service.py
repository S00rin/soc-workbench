"""Read/write application settings stored in SQLite (Module 15).

Secret values are encrypted at rest and never returned in full to the UI.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models.core import Setting
from ..security import decrypt_secret, encrypt_secret, mask_secret

# Keys that must always be encrypted + masked in the UI.
SECRET_KEYS = {
    "llm_api_key",
    "jira_token",
    "jira_password",
    "splunk_token",
    "splunk_password",
    "smtp_password",
    "telegram_token",
    "sms_api_key",
    "webhook_secret",
}

DEFAULTS = {
    # LLM
    "llm_provider": ("anthropic", "llm"),  # anthropic | openai | claude_cli
    "llm_model": ("claude-opus-4-8", "llm"),
    "llm_api_key": ("", "llm"),  # secret (not needed for claude_cli)
    "claude_cli_path": ("", "llm"),  # optional path to `claude`; blank = search PATH
    "llm_max_tokens": ("4096", "llm"),
    "llm_temperature": ("0.3", "llm"),
    "llm_timeout": ("120", "llm"),
    "llm_base_url": ("", "llm"),
    "default_language": ("en", "general"),
    # Jira
    "jira_base_url": ("", "jira"),
    "jira_username": ("", "jira"),
    "jira_token": ("", "jira"),  # secret (API token — Jira Cloud)
    "jira_password": ("", "jira"),  # secret (password — Jira Server/DC)
    "jira_default_project": ("", "jira"),
    "jira_verify_ssl": ("true", "jira"),
    "jira_timeout": ("30", "jira"),
    # Splunk
    "splunk_base_url": ("", "splunk"),
    "splunk_username": ("", "splunk"),
    "splunk_token": ("", "splunk"),  # secret (bearer/HEC token)
    "splunk_password": ("", "splunk"),  # secret (password auth)
    "splunk_verify_ssl": ("true", "splunk"),
    "splunk_allowed_indexes": ("", "splunk"),
    "splunk_max_results": ("1000", "splunk"),
    "splunk_max_timerange": ("-24h", "splunk"),
    "splunk_timeout": ("60", "splunk"),
    # SMTP
    "smtp_host": ("", "smtp"),
    "smtp_port": ("587", "smtp"),
    "smtp_username": ("", "smtp"),
    "smtp_password": ("", "smtp"),  # secret
    "smtp_from": ("", "smtp"),
    "smtp_tls": ("true", "smtp"),
    # Telegram
    "telegram_token": ("", "telegram"),  # secret (bot token)
    "telegram_chat_id": ("", "telegram"),
    # Notifications
    "webhook_secret": ("", "notifications"),  # secret (HMAC signing key)
    # Processing
    "default_protection_mode": ("mask", "processing"),
    "default_optimization_mode": ("balanced", "processing"),
}


def seed_defaults(db: Session) -> None:
    existing = {s.key for s in db.query(Setting.key).all()}
    for key, (value, category) in DEFAULTS.items():
        if key not in existing:
            db.add(
                Setting(
                    key=key,
                    value=value,
                    category=category,
                    is_secret=key in SECRET_KEYS,
                )
            )
    db.commit()


def get_value(db: Session, key: str, default: str = "") -> str:
    row = db.query(Setting).filter(Setting.key == key).first()
    if not row:
        return default
    if row.is_secret:
        return decrypt_secret(row.value)
    return row.value


def get_all_resolved(db: Session) -> dict[str, str]:
    """All settings with secrets decrypted. For internal service use only."""
    result: dict[str, str] = {}
    for row in db.query(Setting).all():
        result[row.key] = decrypt_secret(row.value) if row.is_secret else row.value
    return result


def get_all_safe(db: Session) -> list[dict]:
    """All settings for the UI: secrets are masked, never returned in full."""
    out = []
    for row in db.query(Setting).order_by(Setting.category, Setting.key).all():
        value = row.value
        display = value
        if row.is_secret:
            display = mask_secret(decrypt_secret(value))
        out.append(
            {
                "key": row.key,
                "value": display,
                "is_secret": row.is_secret,
                "category": row.category,
                "has_value": bool(value),
            }
        )
    return out


def set_value(db: Session, key: str, value: str, category: str = "general") -> None:
    is_secret = key in SECRET_KEYS
    row = db.query(Setting).filter(Setting.key == key).first()
    stored = encrypt_secret(value) if is_secret else value
    if row:
        # Empty secret means "leave unchanged" so masked values aren't saved back.
        if is_secret and value == "":
            return
        row.value = stored
        row.is_secret = is_secret
        if category != "general":
            row.category = category
    else:
        db.add(Setting(key=key, value=stored, is_secret=is_secret, category=category))
    db.commit()
