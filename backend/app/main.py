"""SOC Workbench FastAPI application."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import auth, dashboard, documents, iocs, jobs, knowledge, projects
from .api import settings as settings_api
from .config import get_settings
from .database import SessionLocal, init_db
from .jobs.scheduler import shutdown_scheduler, start_scheduler
from .logging_config import get_logger, setup_logging
from .routers import (
    automation, intel, jira, llm, notifications, prompts, reports, search, splunk,
)
from .services import intelligence_automation, settings_service

setup_logging()
logger = get_logger(__name__)
app_settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_settings.ensure_dirs()
    init_db()
    db = SessionLocal()
    try:
        settings_service.seed_defaults(db)
        intelligence_automation.seed_default_sources(db)
    finally:
        db.close()
    start_scheduler()
    logger.info("%s started (env=%s)", app_settings.app_name, app_settings.environment)
    yield
    shutdown_scheduler()
    logger.info("%s shutting down", app_settings.app_name)


app = FastAPI(title=app_settings.app_name, version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (
    auth, settings_api, dashboard, documents, knowledge, iocs, projects, jobs,
    jira, splunk, intel, reports, notifications, prompts, llm, search, automation,
):
    app.include_router(module.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": app_settings.app_name, "version": "0.2.0"}


_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if (_FRONTEND_DIST / "index.html").is_file():
    _assets = _FRONTEND_DIST / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
