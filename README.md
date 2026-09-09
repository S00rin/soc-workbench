# SOC Workbench

A self-hosted analyst workbench for security operations. It ingests documents
and feeds, extracts and tokenizes indicators, organizes investigations into
projects, and runs LLM-assisted analysis — all from a single local process with
an SQLite backing store.

> ⚠️ **Self-hosted security tool.** It ships with development defaults. Change
> `ADMIN_PASSWORD` and `SECRET_KEY`, configure TLS, and read
> [SECURITY.md](SECURITY.md) before exposing it on any network.

## Features

- **Light and dark themes** — switch from the top bar; the browser remembers the choice.
- **Executive and technical dashboards** — an explainable security-posture score with
  period-over-period KPIs, portfolio health, risk register, ATT&CK coverage and a
  downloadable Markdown brief for management; and an engineering view covering the
  IoC/intel pipeline, jobs and scheduler, integrations, telemetry coverage, API
  latency/error rates and storage. Both are feature-gated (`dashboard.executive`,
  `dashboard.technical`) and refresh automatically.
- **Right-side navigation** — begins with About Sorin and adapts to small screens.
- **Analyzer Hub** — a guided Connect → Analyze → Review workspace for connected services.
- **Audit Log** — tenant-scoped administrator history with user/action/status filters, full trace IDs, and CSV export.
- **Input processing** — extract text from PDF, DOCX, XLSX, PPTX, HTML, and
  Markdown, with automatic sensitive-data tokenization. Scanned PDFs and image
  files (PNG/JPG/TIFF/…) are read with OCR (Persian + English).
- **Knowledge base** — store and search extracted content and analyst notes.
- **IoCs** — track indicators of compromise across investigations.
- **Projects** — group documents, indicators, and findings per investigation.
- **Internet intelligence** — pull and normalize RSS/Atom threat feeds.
- **Reports** — assemble and export Markdown/HTML reports.
- **Price Analyzer** — turn a Persian or English contract/SOW into an
  editable person-hour estimate and cost breakdown (user-defined hourly
  rates, overhead/contingency/tax/discount), a 3-level WBS with a Gantt
  schedule, and an editable RACI matrix, exportable to PDF/Excel and linked
  to Projects, Reports and the knowledge base. Accepts scanned/image
  contracts via OCR and defaults to Toman/Farsi.
- **Help guides** — built-in English/Farsi user and admin help guides,
  editable by admins.
- **Atlassian integrations** — tenant-scoped Jira and Confluence connections,
  dynamic Jira field mapping, permission tests, redacted query history, smart
  comment approval, and controlled bulk jobs.
- **SOC KPI and report templates** — daily, weekly, monthly and shift-handover
  Jira report prompts plus backlog, resolution, MTTR, SLA, priority, assignment
  and overdue metrics. Optional Jira timestamp fields unlock MTTA and MTTD.
- **Unified integration chat** — ask Jira, Confluence, Wiki.js and Splunk in
  natural language, edit the generated read-only query, continue with follow-up
  prompts, and reopen the redacted conversation history.
- **Wiki.js** — encrypted API-token connections, GraphQL permission tests, page
  search and prompt-based analysis.
- **Product governance** — multiple local users, module RBAC, activity history,
  and admin-controlled feature start/expiry windows.
- **Sorin assistance** — managed Sorin and optional compatible
  endpoints, with a reusable prompt library and request history. No API key?
  Use the `sorin_cli` (Sorin Code) or `codex_cli` (Sorin Codex) provider to
  run analysis through a local CLI agent with your existing subscription.
- **Background jobs** — scheduled tasks via APScheduler (feed refresh, backups).
- **Notifications** — in-app notification feed for job and system events.
- **Attack Simulation Lab** — classroom profiles for Windows, Linux, web, and
  network behaviors with safe synthetic telemetry, MITRE ATT&CK mapping,
  Splunk detections, and analyst triage guidance.
- **Equipment & Sensor Library** — a catalog of the SOC's devices and sensors
  with capabilities, log sources (sample events, SIEM sourcetype/index, EPS,
  retention, MITRE data sources), log-collection guides, runbooks and
  playbooks. Bilingual (English/Farsi), searchable, exportable to Markdown/JSON,
  and one-click **publish to Confluence** through an existing Atlassian
  connection. Ships with reference profiles (Palo Alto NGFW, Windows Security,
  Microsoft Defender for Endpoint, Zeek).

## Tech stack

| Layer     | Technology                                              |
|-----------|---------------------------------------------------------|
| Backend   | Python 3.12+, FastAPI, SQLAlchemy 2, APScheduler        |
| Database  | SQLite (file-based, under `data/`)                      |
| Frontend  | React 18, TypeScript, Vite, React Router               |
| LLM       | `anthropic` SDK; Sorin-compatible endpoint; or local `sorin`/`codex` CLI (no API key) |
| OCR       | Tesseract (`fas`+`eng`) via pytesseract + pypdfium2 (optional)   |
| Auth      | JWT with database users, module RBAC and encrypted secrets |

See [docs/PRODUCT_GUIDE.md](docs/PRODUCT_GUIDE.md) for product usage,
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for a deeper technical walkthrough, and
[docs/PROJECT_REVIEW.md](docs/PROJECT_REVIEW.md) for the current code review,
prioritised improvement plan, dashboard metric definitions and advanced roadmap.

## Quick start

### 1. Configure

```bash
cp .env.example .env
```

Edit `.env` and, at minimum, change `ADMIN_PASSWORD` and `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"   # -> SECRET_KEY
```

### 2. Backend

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The API is served under `http://127.0.0.1:8000/api`. Health check:
`GET /api/health`.

**Optional — OCR for scanned PDFs and images.** Text-based files work out of
the box. To read scanned/image documents you also need the Tesseract engine
and language packs installed on the host:

```bash
# Debian/Ubuntu
sudo apt-get install tesseract-ocr tesseract-ocr-fas tesseract-ocr-eng poppler-utils
```

Without it, text-based extraction still works and image/scanned input returns
a clear "install Tesseract" message instead of failing silently.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev        # dev server at http://localhost:5173 (proxies /api -> :8000)
```

On the first upgraded start, the initial admin account is seeded from
`ADMIN_USERNAME` / `ADMIN_PASSWORD`. Create additional users and module access
rules under **Access & Features**.

### Single-process (production-style)

Build the frontend and let the backend serve it — no separate web server:

```bash
cd frontend && npm run build      # emits frontend/dist
cd ../backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

When `frontend/dist/index.html` exists, the backend serves the SPA for all
non-`/api` routes.

## Docker customer image

```bash
cp .env.example .env
# Set strong ADMIN_PASSWORD and SECRET_KEY values in .env first.
docker compose build
docker compose up -d
docker compose ps
```

The multi-stage image serves the full product and excludes proprietary `.py`,
`.ts` and `.tsx` source from the final stage. It runs as a non-root user with a
read-only filesystem and a persistent data volume. See
[customer Docker deployment](docs/CUSTOMER_DEPLOYMENT.md) for image inspection,
private-registry delivery, backups, upgrades, and the limits of on-premises
source protection.

## Configuration

All configuration is via environment variables (see `.env.example`).
Non-secret operational settings (model names, timeouts) can also be changed at
runtime in the **Settings** UI and are stored in the database. Key variables:

| Variable                 | Purpose                                             |
|--------------------------|-----------------------------------------------------|
| `ADMIN_USERNAME/PASSWORD`| Initial administrator credentials (first seed)      |
| `SECRET_KEY`             | Signs JWTs **and** encrypts stored secrets — set it |
| `DATA_DIR`               | Where SQLite DB, uploads, reports, backups live     |
| `CORS_ORIGINS`           | Allowed frontend origins (comma-separated)          |
| `ANTHROPIC_API_KEY`      | Sorin API key (optional; also settable in UI)      |
| `COMPATIBLE_BASE_URL/KEY`    | Optional Sorin-compatible endpoint                 |
| `ATLASSIAN_OAUTH_*`      | Optional Jira/Confluence Cloud OAuth 2.0 (3LO) app  |
| `ATLASSIAN_BULK_MAX_ISSUES` | Hard ceiling for one bulk comment job            |
| `ATLASSIAN_HISTORY_RETENTION_DAYS` | Default history retention policy        |

See [Atlassian integration setup](docs/ATLASSIAN_INTEGRATION.md) for Jira
Cloud/Data Center, Confluence, OAuth scopes, migration, deployment, and
rollback instructions.

See [Product governance, prompt chat and Wiki.js](docs/PRODUCT_GOVERNANCE_AND_WIKIJS.md)
for user roles, feature expiry, Wiki.js API setup, deployment and rollback.

See [Price Analyzer](docs/PRICE_ANALYZER.md) for the contract analysis,
WBS/Gantt/RACI and cost estimation workflow.

See [Equipment & Sensor Library](docs/EQUIPMENT_SENSORS.md) for the sensor
catalog, log-source documentation, runbooks/playbooks and Confluence publishing.

## Data & storage

Everything the app generates lives under `data/` (git-ignored):

```
data/
├── app.db        # SQLite database
├── uploads/      # ingested documents
├── reports/      # generated reports
├── exports/      # exported artifacts
├── backups/      # database backups
├── cache/        # intel/feed cache
└── logs/         # application logs
```

## Testing

```bash
cd backend
pytest

cd ../frontend
npm run typecheck
npm test
npm run build
```

## Project layout

```
soc-workbench/
├── backend/
│   └── app/
│       ├── api/        # core endpoints (auth, documents, iocs, projects, ...)
│       ├── routers/    # integrations (jira, splunk, intel, reports, llm, ...)
│       ├── services/   # extraction, tokenization, LLM, jobs, notifier, ...
│       ├── models/     # SQLAlchemy models
│       ├── jobs/       # APScheduler background scheduler
│       └── main.py     # app entrypoint
├── frontend/
│   └── src/
│       ├── pages/      # one page per feature area
│       └── components/
└── data/               # runtime data (git-ignored)
```

## License

No license file is included yet — all rights reserved by default. Add a
`LICENSE` file if you intend to share or open-source this project.


## Intelligence and Sorin automation

The **Automation** page provides editable news/IoC sources (add, update, disable,\ndelete, or run on demand) and three local workflows:

- Scheduled RSS/Atom collection with SOC scope scoring. Cloud security, API
  security, Web3, and cryptocurrency-only content is rejected. Accepted items
  are saved directly to the Knowledge Base and their IoCs are extracted.
- Built-in IoC adapters for ThreatFox, URLhaus, and CISA KEV. Values are
  normalized, non-public IPv4 addresses are rejected, and source observations\n  are retained for correlation. All Knowledge Base content is also scanned for\n  valid indicator-shaped values during scheduled and on-demand runs.
- Sorin Code tasks in `plan`, `read-only`, or `edit` mode. Task
  workspaces must be under `SORIN_WORKSPACE_ROOT`. Edit mode permits file
  editing but does not enable Bash or bypass Sorin Code permissions.

The scheduler starts with the application, polls every 15 minutes, and runs each\nsource according to its editable interval. Manual collection is available from the Automation page or through
`POST /api/automation/run-all`.

> Sorin Code must be installed and authenticated on the host running SOC
> Workbench. Keep `SORIN_WORKSPACE_ROOT` narrow; do not point it at your home
> directory or a directory containing secrets.
