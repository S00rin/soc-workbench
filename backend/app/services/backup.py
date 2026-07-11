"""Backup / restore (Backup and Restore section).

Creates a timestamped zip of the SQLite DB, uploads, and reports. Settings can
be exported WITHOUT secrets.
"""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings
from ..logging_config import get_logger

logger = get_logger(__name__)


def create_backup() -> Path:
    s = get_settings()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = s.backups_dir / f"backup-{ts}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        if s.sqlite_path.exists():
            zf.write(s.sqlite_path, "app.db")
        for folder in (s.uploads_dir, s.reports_dir):
            for f in folder.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(s.data_dir).as_posix())
    logger.info("Backup created: %s", out.name)
    return out


def restore_backup(zip_path: Path) -> None:
    s = get_settings()
    if not zip_path.exists():
        raise FileNotFoundError(f"Backup not found: {zip_path}")
    with zipfile.ZipFile(zip_path) as zf:
        # DB first.
        if "app.db" in zf.namelist():
            with zf.open("app.db") as src, open(s.sqlite_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
        for member in zf.namelist():
            if member == "app.db":
                continue
            target = s.data_dir / member
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    logger.info("Restored from %s", zip_path.name)


def export_settings_no_secrets(safe_settings: list[dict]) -> Path:
    """Write non-secret settings to data/exports as JSON."""
    s = get_settings()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = s.exports_dir / f"settings-{ts}.json"
    clean = [row for row in safe_settings if not row.get("is_secret")]
    out.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    return out
