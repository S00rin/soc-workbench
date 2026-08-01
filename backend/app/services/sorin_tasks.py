"""Constrained Sorin Code runner for explicitly allow-listed workspaces."""
from __future__ import annotations

import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings
from ..database import SessionLocal
from ..models.automation import SorinTask

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sorin-task")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _allowed_workspace(path: str) -> Path:
    settings = get_settings()
    root = Path(getattr(settings, "sorin_workspace_root", "") or settings.data_dir.parent).resolve()
    workspace = Path(path).expanduser().resolve()
    if workspace != root and root not in workspace.parents:
        raise ValueError(f"Workspace must be inside allow-listed root: {root}")
    if not workspace.is_dir():
        raise ValueError("Workspace does not exist")
    return workspace


def _git_files(workspace: Path) -> set[str]:
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"], cwd=workspace, capture_output=True,
            text=True, timeout=20, check=False,
        )
        return {line[3:].strip() for line in proc.stdout.splitlines() if len(line) > 3}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()


def execute(task_id: int) -> None:
    db = SessionLocal()
    task = db.get(SorinTask, task_id)
    if not task:
        db.close()
        return
    try:
        workspace = _allowed_workspace(task.workspace)
        exe = shutil.which("sorin") or "sorin"
        tools = {
            "plan": "Read,Grep,Glob",
            "read-only": "Read,Grep,Glob",
            "edit": "Read,Edit,Write,Grep,Glob",
        }.get(task.mode)
        if tools is None:
            raise ValueError("Mode must be plan, read-only, or edit")
        before = _git_files(workspace)
        task.status = "running"
        task.started_at = _now()
        db.commit()
        cmd = [
            exe, "-p", "--output-format", "json", "--strict-mcp-config",
            "--tools", tools, "--max-turns", str(max(1, min(task.max_turns, 50))),
            "--setting-sources", "project",
        ]
        if task.mode == "plan":
            cmd += ["--permission-mode", "plan"]
        proc = subprocess.run(
            cmd, input=task.prompt, cwd=workspace, capture_output=True, text=True,
            encoding="utf-8", timeout=max(30, min(task.timeout_seconds, 3600)),
        )
        task.return_code = proc.returncode
        if proc.returncode:
            task.status = "failed"
            task.error = (proc.stderr or proc.stdout)[-4000:]
        else:
            try:
                payload = json.loads(proc.stdout)
                task.output = payload.get("result", proc.stdout)
                if payload.get("is_error"):
                    task.status = "failed"
                    task.error = str(payload.get("result") or payload.get("subtype"))
                else:
                    task.status = "completed"
            except json.JSONDecodeError:
                task.output = proc.stdout
                task.status = "completed"
        task.changed_files = sorted(_git_files(workspace) - before)
    except subprocess.TimeoutExpired as exc:
        task.status = "failed"
        task.error = f"Sorin Code timed out after {exc.timeout}s"
    except Exception as exc:
        task.status = "failed"
        task.error = str(exc)
    finally:
        task.finished_at = _now()
        db.commit()
        db.close()


def submit(task_id: int) -> None:
    _pool.submit(execute, task_id)
