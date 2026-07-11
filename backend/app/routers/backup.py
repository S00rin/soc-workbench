"""Backup / restore (Backup and Restore section)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..security import get_current_user
from ..services import backup as backup_svc
from ..services.settings_service import get_all_safe

router = APIRouter(prefix="/api/backup", tags=["backup"])
settings = get_settings()


@router.get("")
def list_backups(user: str = Depends(get_current_user)):
    files = sorted(settings.backups_dir.glob("backup-*.zip"), reverse=True)
    return [{"name": f.name, "size": f.stat().st_size} for f in files]


@router.post("/create")
def create(user: str = Depends(get_current_user)):
    path = backup_svc.create_backup()
    return {"ok": True, "file": path.name}


@router.get("/download/{name}")
def download(name: str, user: str = Depends(get_current_user)):
    # Prevent path traversal.
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "Invalid name")
    path = settings.backups_dir / name
    if not path.exists():
        raise HTTPException(404, "Backup not found")
    return FileResponse(str(path), filename=name)


class RestoreRequest(BaseModel):
    name: str


@router.post("/restore")
def restore(req: RestoreRequest, user: str = Depends(get_current_user)):
    if "/" in req.name or "\\" in req.name or ".." in req.name:
        raise HTTPException(400, "Invalid name")
    path = settings.backups_dir / req.name
    try:
        backup_svc.restore_backup(Path(path))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return {"ok": True, "restored": req.name}


@router.post("/export-settings")
def export_settings(db: Session = Depends(get_db), user: str = Depends(get_current_user)):
    path = backup_svc.export_settings_no_secrets(get_all_safe(db))
    return {"ok": True, "file": path.name}
