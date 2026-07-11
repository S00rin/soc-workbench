# Architecture

SOC Workbench is a single-process application: a FastAPI backend that also
serves a compiled React single-page app. State lives in a local SQLite
database; there are no external service dependencies required to run it.

```
┌───────────────────────────────────────────────────────────────┐
│                         Browser (SPA)                           │
│  React + Vite + React Router  →  calls /api/*                   │
└───────────────────────────────┬───────────────────────────────┘
                                 │  (dev: Vite proxies /api → :8000)
                                 ▼
┌───────────────────────────────────────────────────────────────┐
│                       FastAPI application                       │
│                                                                 │
│  app/api/       core endpoints                                  │
│  app/routers/   integrations & roadmap features                │
│  app/services/  business logic (extraction, LLM, jobs, ...)     │
│  app/models/    SQLAlchemy ORM models                           │
│  app/jobs/      APScheduler background scheduler                │
│                                                                 │
│  Serves frontend/dist for all non-/api routes when built        │
└───────────────────────────────┬───────────────────────────────┘
                                 ▼
                 ┌───────────────────────────────┐
                 │   SQLite (data/app.db)         │
                 │   + files under data/          │
                 └───────────────────────────────┘
```

## Request lifecycle

1. On startup (`lifespan` in `app/main.py`) the app ensures data directories
   exist, initializes the database schema, and seeds default settings.
2. CORS middleware is applied using `CORS_ORIGINS`.
3. Routers are registered under `/api/*`. Core modules load from `app.api`;
   integrations load from `app.routers`.
4. If `frontend/dist/index.html` exists, a catch-all route serves the SPA and
   its assets for any path that is not `/api/*`.

## Backend modules

### `app/api/` — core endpoints
`auth`, `dashboard`, `documents`, `knowledge`, `iocs`, `projects`, `jobs`,
`settings`.

### `app/routers/` — integrations & extended features
`jira`, `splunk`, `intel`, `reports`, `notifications`, `prompts`, `llm`,
`search`, plus additional `backup`, `inputs`, and per-feature routers.

### `app/services/` — business logic
- `document_processing`, `extract` — pull text out of PDF/DOCX/XLSX/PPTX/HTML.
- `sensitive_data` — tokenize/detokenize sensitive strings; the reversible
  mapping is encrypted at rest with `SECRET_KEY`.
- `entities`, `optimizer` — entity extraction and content optimization.
- `intel_collector` — fetch and normalize RSS/Atom threat feeds.
- `llm` — provider abstraction over Anthropic (and OpenAI-compatible) APIs.
- `jira_client`, `splunk_client` — thin integration clients.
- `report_builder` — assemble Markdown/HTML reports.
- `notifier` — emit in-app notifications.
- `backup` — database backup/restore.
- `settings_service` — runtime settings persisted in the DB.

### `app/jobs/`
`scheduler` wires APScheduler for recurring background work (feed refresh,
backups). Started as part of the application lifespan.

## Data model & storage

SQLAlchemy models live in `app/models/` (`core`, `content`, `entities`, plus a
shared `base`). The database URL defaults to
`sqlite:///<DATA_DIR>/app.db` and can be overridden via `DATABASE_URL`.

Generated artifacts (uploads, reports, exports, backups, cache, logs) are
written under `DATA_DIR` and are excluded from version control.

## Configuration precedence

1. **Environment / `.env`** — all secrets and bootstrap config (loaded by
   `pydantic-settings` in `app/config.py`).
2. **Database-backed settings** — non-secret operational values (model names,
   timeouts, feature toggles) editable at runtime via the Settings UI, seeded
   from defaults on first boot.

## Frontend

A Vite + React + TypeScript SPA. Each feature area maps to a page under
`src/pages/` (Dashboard, Process, Knowledge, IoCs, Projects, Jobs, Intel, Jira,
Splunk, Reports, Notifications, Prompts, Settings, Login). API access is
centralized in `src/api.ts`. In development, Vite proxies `/api` to the backend
on port 8000 so the SPA and API share an origin.
