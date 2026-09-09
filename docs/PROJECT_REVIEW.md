# SOC Workbench — Project Review, Improvement Plan and Advanced Roadmap

_Review date: 2026-09-09 · Codebase at `main` (`e00dbee`) plus the executive/technical dashboards added alongside this document._

This document has four parts:

1. [What is working well](#1-what-is-working-well)
2. [Findings and recommended improvements](#2-findings-and-recommended-improvements) (prioritised)
3. [The executive and technical dashboards](#3-executive-and-technical-dashboards) (shipped with this review)
4. [Advanced feature roadmap](#4-advanced-feature-roadmap)

Severity legend: **P1** fix soon (security, data loss, correctness) · **P2** important for maintainability or scale · **P3** polish.

---

## 1. What is working well

- **Clear single-process architecture.** FastAPI + SQLite + built SPA served from one
  process is the right fit for an on-prem analyst tool. Zero external services makes
  installation and the hardened Docker image straightforward.
- **Governance is real, not cosmetic.** `ProductAccessMiddleware` enforces module RBAC and
  time-bounded feature policies for every `/api/*` route on the backend; the frontend only
  mirrors it. Feature keys make it possible to sell/enable capabilities per customer.
- **Data-protection by design.** Sensitive-data tokenisation before any LLM call, encrypted
  token mappings and connector credentials at rest, redacted integration history, and a
  read-only query model for the integration chat (bounded JQL/CQL/SPL) show good threat
  modelling for an LLM-assisted SOC tool.
- **Deterministic KPIs with honest gaps.** `jira_kpis.calculate_soc_kpis` refuses to guess
  MTTA/MTTD without configured fields and records `data_quality.missing`. The same
  philosophy was used for the new posture score.
- **Bilingual (FA/EN) product surface** including OCR, PDF shaping and help guides — rare and
  valuable for the target market.
- **Provider abstraction for Atlassian/Wiki.js/Splunk** (transport, error classification,
  retry, history, audit) is a solid base for a plugin SDK.
- **Sensible test coverage of business logic** (82 backend tests, provider mocks with
  `httpx.MockTransport`, frontend sanitiser/navigation tests).

---

## 2. Findings and recommended improvements

### 2.1 Architecture and code health

| # | Sev | Finding | Recommendation |
|---|-----|---------|----------------|
| A1 | P2 | **Dead duplicate routers.** `app/routers/{auth,backup,dashboard,inputs,iocs,jobs,knowledge,projects,settings}.py` are never imported (only `app/api/*` versions are registered in `main.py`). Two `/api/dashboard` implementations exist with different payloads. | Delete the unused modules (or move any still-needed behaviour, e.g. `backup.py` routes, into `app/api`). Add a test that asserts every module in `app/routers` and `app/api` is included in `app.routes` to prevent regressions. |
| A2 | P2 | **Two authorisation styles.** 26 router/API modules use `get_current_user` (username string only) while newer code uses `AuthContext`. The former cannot scope by tenant or role. | Standardise on `get_auth_context`. Replace `user: str = Depends(get_current_user)` mechanically; it unblocks tenant scoping (A3). |
| A3 | P2 | **Core tables are global, governance tables are tenant-scoped.** `IoC`, `Project`, `Document`, `KnowledgeItem`, `Report`, `Job`, `IntelItem` have no `tenant_id`, while Atlassian/governance/sensor tables do. The dashboard therefore mixes tenant-scoped and global counts. | Add `tenant_id` (default `"default"`, indexed) to core tables in a migration `v0008`, populate from `default_tenant_id`, and filter in every query via a small `tenant_query(db, Model, ctx)` helper. This is the prerequisite for MSSP mode (§4). |
| A4 | P2 | **Schema management is split** between hand-written migrations and `Base.metadata.create_all` for "legacy" tables; new columns on legacy tables silently never appear on upgraded databases. | Either adopt Alembic (autogenerate + review) or make the rule explicit: _every_ schema change is a migration, `create_all` only bootstraps fresh installs. Add a CI check that creates a DB from `v0001` and asserts `Base.metadata` matches (`sqlalchemy-diff`/`alembic check`). |
| A5 | P2 | **`schemas.py` is a single 300-line module** and most integration routers define their own Pydantic models inline; the dashboard returns untyped `dict`s. | Split schemas per domain (`schemas/dashboard.py`, ...) and type the new dashboard payloads with `TypedDict`/Pydantic so the frontend can generate types (`openapi-typescript`). |
| A6 | P3 | **`passlib[bcrypt]` is a dependency but unused** (passwords use `hashlib.scrypt`). | Remove it; fewer wheels, smaller image, fewer CVE alerts. |
| A7 | P3 | **Broad `except Exception`** in 12 places, some swallowing errors into empty strings (`decrypt_secret` returns `""` on failure). | Log with `logger.exception` and surface a typed error; for `decrypt_secret` distinguish "no value" from "key mismatch" so an operator learns that `SECRET_KEY` changed. |

### 2.2 Security

| # | Sev | Finding | Recommendation |
|---|-----|---------|----------------|
| S1 | P1 | **Single `SECRET_KEY` is used both to sign JWTs and to derive the Fernet key** for all encrypted secrets and token mappings. A leaked JWT signing key decrypts every stored credential; rotating it invalidates all stored secrets at once. | Derive two keys with HKDF (`info=b"jwt"`, `info=b"fernet"`) from `SECRET_KEY`, and support **key rotation** for Fernet via `MultiFernet` with a `SECRET_KEY_PREVIOUS` env var plus a re-encrypt command. |
| S2 | P1 | **Bearer token in `localStorage` with a 7-day lifetime and no revocation.** Any XSS (the Markdown sanitiser is good but is the only line of defence) yields a week-long session; logout only deletes the token client-side. | Short-lived access token (15–60 min) + rotating refresh token in an `HttpOnly; Secure; SameSite=Strict` cookie, server-side session table with revoke-on-logout / revoke-all-on-password-change, and a strict CSP header (`default-src 'self'`). |
| S3 | P2 | **OpenAPI docs are exposed in production** (`/docs`, `/openapi.json` default). Useful for analysts, but it also gives attackers the full attack surface. | `docs_url=None` when `ENVIRONMENT=production` unless `EXPOSE_API_DOCS=true`. |
| S4 | P2 | **No security response headers** (CSP, HSTS, X-Content-Type-Options, Referrer-Policy, Permissions-Policy). | Add a small `SecurityHeadersMiddleware`; the SPA is static so a strict CSP is achievable (inline styles are the only exception to handle). |
| S5 | P2 | **Login rate limiting is in-memory and per-process**; it resets on restart and does not cover `X-Forwarded-For` spoofing when behind a proxy without `--forwarded-allow-ips`. | Persist attempts in SQLite (or move to a `login_attempts` table with TTL) and add per-account lockout with admin unlock; alert to the notification feed. |
| S6 | P2 | **Prompt-injection surface**: connector data (Jira comments, Confluence pages, RSS bodies) is placed into LLM context. Mitigations exist (read-only queries, redaction) but there is no explicit instruction-hierarchy defence or output validation for generated JQL/SPL beyond the allow-list. | Wrap untrusted content in delimiters with an explicit "data, not instructions" system message; validate generated queries with a parser (e.g. reject SPL commands outside an allow-list rather than string checks); add canary tokens to detect exfiltration attempts in outputs. |
| S7 | P3 | Default `.env.example` values (`changeme`, `dev-insecure-secret-change-me`) are accepted at startup. | Refuse to start with `ENVIRONMENT=production` and default secrets; warn loudly otherwise (the README already asks — enforce it). |

### 2.3 Data, reliability and operations

| # | Sev | Finding | Recommendation |
|---|-----|---------|----------------|
| R1 | P1 | **Backups copy the live SQLite file** (`zipfile.write(sqlite_path)`) while writers may be active, risking a torn/corrupt backup. | Use the SQLite online backup API (`sqlite3.Connection.backup`) or `VACUUM INTO` to a temp file, then zip that. Verify with `PRAGMA integrity_check` and record the result in the job. |
| R2 | P1 | **Jobs that were `running` when the process died stay `running` forever**; retry closures live only in memory (`_fns`) so "retry" fails after any restart. | On startup mark stale `running`/`pending` rows as `failed` ("interrupted by restart"); make job kinds re-dispatchable from a registry (`kind -> callable(ref_id)`) rather than closures so retries survive restarts. |
| R3 | P2 | **Unbounded growth**: `user_activity` receives one row per API request with no retention (the new technical dashboard makes this visible), `intel_items` and `jobs` also grow without limit. `TimestampMixin.created_at` is not indexed, so time-window queries scan. | Add `retention_days` settings per table and a nightly purge job (the pattern exists for `IntegrationHistory`); add indexes on `created_at` for `user_activity`, `jobs`, `intel_items`, `iocs`. Consider sampling read-only GETs in the activity log. |
| R4 | P2 | **Activity logging is synchronous and opens a second DB session per request**, doubling SQLite write pressure and adding latency to every call. | Buffer activity rows in a bounded in-memory queue flushed by a background task every second (or per 100 rows). Enable SQLite WAL mode (`PRAGMA journal_mode=WAL`) and `synchronous=NORMAL` in `database.py`. |
| R5 | P2 | **Scheduler and worker run inside the web process** (fine for one node) but there is no lock, so running two replicas would double-collect feeds and back up twice. | Document single-replica requirement, and add a lightweight leader lock (`schema_migrations`-style row with heartbeat) so a second instance skips scheduling. |
| R6 | P3 | No health detail endpoint; `/api/health` cannot tell an operator whether the scheduler is alive or the DB is writable. | Add `/api/health/ready` returning scheduler state (`describe_jobs()` now exists), DB write check, disk free space and last backup age. |

### 2.4 Frontend

| # | Sev | Finding | Recommendation |
|---|-----|---------|----------------|
| F1 | P2 | **`strict: false` and 178 explicit `any`s**; API payloads are untyped so refactors on the backend break the UI silently. | Turn on `strict` incrementally (`noImplicitAny` first), generate API types from OpenAPI, and type page props. |
| F2 | P2 | **No linter/formatter** (no ESLint/Prettier config), and no `react-hooks` rules, despite `eslint-disable` comments in code. | Add `eslint` with `@typescript-eslint`, `react-hooks`, `jsx-a11y`; run in CI. |
| F3 | P2 | **One 500 kB+ JS chunk**; d3 (used only by `SorinGraph`) and `marked` are in the main bundle. | `React.lazy` per route (hubs, Attack Lab, About Sorin, Price Analyzer) and dynamic-import d3. |
| F4 | P3 | Testing Library auto-cleanup was not active (no `globals: true`), so DOM leaked between tests in a file. | Set `test.globals: true` in `vitest.config.ts` or call `cleanup` in `setup.ts` (the new dashboard test does this locally). |
| F5 | P3 | Several dark-only hard-coded colours (`.hub-tabs`, `.badge.*`, Attack Lab, chat bubbles) break the light theme. | Move remaining hard-coded colours to CSS variables; the badges and hub tabs were fixed in this change. |
| F6 | P3 | Accessibility: icon-only buttons without labels in some pages, tables without captions, colour-only status indicators. | Add `aria-label`s, keep text alongside colour (the dashboards use text badges), and run `axe` in vitest. |

### 2.5 CI/CD, packaging and documentation

| # | Sev | Finding | Recommendation |
|---|-----|---------|----------------|
| C1 | P1 | **CI runs only one backend test file** (`pytest tests/test_intelligence_automation.py`), and **never runs `npm run typecheck` or `npm test`**. Most of the suite (and the new dashboard tests) is not gated. | Run `pytest -q` (whole suite), `npm run typecheck`, `npm test`, `npm run build`; add `pip-audit`, `npm audit --audit-level=high`, `ruff`, and a Docker build job. |
| C2 | P2 | No dependency update automation, no SBOM, image is unsigned. | Dependabot/Renovate; `syft` SBOM and `cosign` signing in the release workflow; pin base images by digest. |
| C3 | P3 | Docs are good but `ARCHITECTURE.md` lists modules that are dead (A1) and says "single-user" in places that are now multi-user. | Refresh after A1/A2; add an ADR folder for decisions such as SQLite-only, single-process, and the posture score weights. |

### 2.6 Suggested order of work

1. **P1 batch (small, high value):** R1 safe backups · R2 job reconciliation · S1 key separation + rotation · S2 session hardening + CSP · C1 CI covering everything.
2. **Foundation batch:** A1 delete dead code · A2 `AuthContext` everywhere · A3 `tenant_id` on core tables · R3/R4 retention, WAL, async activity log · F1/F2 types + lint.
3. **Then** the roadmap in §4, most of which depends on A3 (tenancy) and A2 (context).

---

## 3. Executive and technical dashboards

Shipped with this review (see PR). Both are computed on demand from SQLite by
`app/services/dashboard_metrics.py`, exposed under `/api/dashboard/*`, module-gated
(`dashboard`) and individually feature-gated (`dashboard.executive`, `dashboard.technical`)
so an admin can turn either view on/off or time-box it per customer.

### Executive view (`/?view=executive`, `GET /api/dashboard/executive?days=30`)

Audience: SOC manager, CISO, customer sponsor.

- **Security posture score (0–100, grade A–F)** — a weighted composite that is fully
  explainable: every component shows its weight, score and the raw evidence
  (e.g. "10/14 ATT&CK tactics covered by active sensors"). Components that cannot be
  measured (no integrations, no jobs) are marked `n/a` and excluded, never counted as zero.

  | Component | Weight | Source |
  |---|---|---|
  | Detection coverage | 20% | active sensors' `mitre_tactics` vs the 14 enterprise tactics |
  | Integration readiness | 15% | connections healthy / total |
  | Automation reliability | 15% | completed / finished jobs in period |
  | Intelligence freshness | 15% | enabled sources fresh (never-run sources excluded) |
  | Investigation health | 15% | green=100 / yellow=50 / red=0 over active projects |
  | IoC hygiene | 10% | 1 − (false positives + expired) / total |
  | Governance | 10% | −20 per feature policy expiring within 30 days |

- **KPI cards with period-over-period deltas** (new IoCs, intel items, documents, reports,
  knowledge, engaged users/activity) plus automation success, integration readiness,
  ATT&CK coverage.
- **Trends** (daily sparklines), **Needs attention** (rule-based, severity-ranked, deep-linked),
  **Investigation portfolio** (health donut + table), **Risk register** (normalised from
  project risk JSON), **Detection coverage grid**, governance/continuity panels.
- **Download brief (.md)** and **Save to Reports** (creates a draft `executive` report) so the
  view feeds the existing reporting workflow.

### Technical view (`/?view=technical`, `GET /api/dashboard/technical?days=7`)

Audience: SOC engineer, platform owner, on-shift lead.

- **IoC analytics** — by type/severity/confidence, false-positive ratio, expired/expiring,
  multi-source-corroborated indicators, top sources, latest high/critical.
- **Intelligence pipeline** — per-source status (`healthy / stale / failing / never_run /
  disabled`, staleness = 3× interval), yield by category and source, relevance.
- **Background jobs & scheduler** — success rate, avg/p95 duration, status-by-kind matrix,
  live APScheduler next-run times, recent failures.
- **Integrations** — connection states, operation history success/latency, top error codes,
  chat turn error rate and latency.
- **Telemetry & detection coverage** — sensors by category/status/criticality, EPS by sensor,
  tactic matrix, log sources without a SIEM index, sensors without playbooks/runbooks.
- **API performance** — from the activity log: hourly volume with errors, p50/p95/max
  latency, status classes, per-module error rate, slowest endpoints. Non-admins see only
  their own activity (same rule as the existing dashboard).
- **Storage / content / data protection** — data-dir footprint, backups, documents and
  analyses inventory, token estimates, protected token mappings, enabled patterns.

Both views accept a period selector (`days`), refresh automatically every 60 s (toggle is
persisted), and are covered by backend tests (`tests/test_dashboard_metrics.py`) and
frontend tests (`src/pages/Dashboard.test.tsx`).

---

## 4. Advanced feature roadmap

Grouped by horizon. Each item lists what it builds on so the sequencing is clear.

### Now (builds directly on existing modules)

1. **Silent-sensor and feed-anomaly detection.** Use the sensor library's `eps_estimate` and
   the intel pipeline's daily yield as baselines; alert (notification + attention item) when
   a Splunk sourcetype's real EPS drops below X% of expected or a feed's yield collapses.
   Builds on: technical dashboard metrics, Splunk client, notifier.
2. **Scheduled executive brief delivery.** Nightly/weekly job renders the executive brief
   (Markdown → PDF via the existing reportlab/bidi stack, FA/EN), stores it in Reports and
   publishes to Confluence through the existing Atlassian connection.
   Builds on: `render_executive_brief`, report_builder, confluence_provider, scheduler.
3. **IoC lifecycle engine.** Confidence decay by age and source trust, automatic expiry,
   sighting counts from Splunk retro-hunts (`index=* [values]` bounded search), promotion to
   "watchlist" export (CSV/STIX) for firewalls/EDR.
   Builds on: IoC/IoCObservation, `IoCSource.trust_score`, Splunk client.
4. **Health/readiness endpoint and Prometheus `/metrics`.** Export the technical dashboard
   counters so existing monitoring stacks can alert on the platform itself.

### Next (needs A2/A3 foundations)

5. **Case management with an evidence graph.** A `Case` entity linking documents, IoCs,
   analyses, Jira issues, Confluence pages and sensors, with a timeline, tasks and a
   d3-rendered relationship graph (the `SorinGraph` component is a starting point).
   Export as STIX 2.1 bundle; import STIX/TAXII feeds into intel.
6. **Detection-as-code with coverage diff.** Store Sigma rules per sensor/log source,
   compile to SPL (pySigma), push to Splunk saved searches, and compute ATT&CK technique
   coverage from _deployed_ detections rather than declared tactics; show the delta vs the
   sensor library's claimed coverage on the executive/technical dashboards.
7. **Detection validation via the Attack Lab.** Emit the lab's synthetic telemetry into a
   Splunk test index and assert that the mapped detections fire; produce a purple-team
   scorecard (tested / fired / missed) per scenario.
8. **Alert triage copilot.** Ingest Splunk notables/Jira alerts, run tokenised LLM triage
   with a fixed schema (verdict, confidence, evidence, next steps), require analyst
   confirmation, and learn calibration from analyst overrides (precision per rule shown on
   the technical dashboard).
9. **Agentic playbooks (SOAR-lite).** Declarative YAML playbooks (trigger → steps →
   approvals) using the existing providers as idempotent actions (comment, transition,
   search, publish page, notify). Human-in-the-loop approvals reuse the bulk-operation
   approval and idempotency machinery; every step lands in the audit log with a dry-run mode.
10. **Semantic search / RAG over the knowledge base.** Local embeddings
    (`sentence-transformers` or the compatible endpoint) stored in `sqlite-vec`; answers
    cite knowledge items, honour tokenisation (embeddings computed on protected text) and
    module RBAC.

### Later (platform-level)

11. **MSSP multi-tenant mode.** Tenant on every table (A3), per-tenant data directories and
    encryption keys, tenant switcher for MSSP admins, and **signed, expiring share links**
    for a read-only customer-facing executive dashboard (no login required, scoped token).
12. **Threat-actor knowledge graph.** Normalise entities from intel and documents (actors,
    malware, CVEs, TTPs, infrastructure) into a graph with MITRE ATT&CK/CAPEC/CWE
    enrichment; graph queries power "who else uses this C2" style pivots.
13. **SLA engine and shift operations.** Real MTTA/MTTR from Jira changelog transitions
    (not only custom fields), SLA policies per customer/priority with breach prediction,
    shift roster, and automated handover notes generated from the day's activity.
14. **Plugin SDK for integrations.** Formalise the provider interface (auth, test, search,
    read, optional write, redaction hints) as an entry-point based plugin system so
    customers can add EDR/SIEM/ticketing connectors without touching core.
15. **Offline / air-gapped profile.** Local LLM via an Ollama-compatible endpoint (already
    supported), bundled feeds via file drop, offline ATT&CK data, and a documented no-egress
    configuration verified by a test that fails on any outbound call.
16. **Observability and audit exports.** OpenTelemetry tracing of every connector call and
    LLM request (correlation IDs already exist), SIEM-friendly audit log export (CEF/JSON
    over syslog) so the workbench itself is monitored by the SOC it serves.
17. **Supply-chain hardening for the customer image.** SBOM, cosign signatures, provenance
    attestations, reproducible builds, CVE scanning gate in CI, and a `soc-workbench doctor`
    command that verifies image integrity and configuration on the customer host.
