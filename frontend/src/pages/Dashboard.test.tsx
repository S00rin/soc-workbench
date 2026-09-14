import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AccessProvider, AccessState } from "../access";
import { ToastProvider } from "../lib";
import Dashboard from "./Dashboard";

vi.mock("../api", () => ({
  api: { get: vi.fn(), post: vi.fn(), download: vi.fn(), patch: vi.fn() },
}));
import { api } from "../api";

const comparison = (value: number, previous: number) => ({ value, previous, delta: value - previous, delta_pct: previous ? Math.round((value - previous) / previous * 100) : null });
const series = (count: number) => Array.from({ length: 7 }, (_, i) => ({ date: `2026-09-0${i + 1}`, count }));

const executivePayload = {
  generated_at: "2026-09-09T12:00:00+00:00",
  period: { days: 30, since: "2026-08-10T12:00:00+00:00", until: "2026-09-09T12:00:00+00:00" },
  posture: { score: 72, grade: "C", components: [
    { key: "detection_coverage", label: "Detection coverage", score: 71.4, weight: 0.2, detail: "10/14 tactics" },
    { key: "integration_readiness", label: "Integration readiness", score: null, weight: 0.15, detail: "0/0" },
  ] },
  kpis: {
    active_investigations: 3, red_investigations: 1, avg_progress: 55,
    iocs_new: comparison(12, 4), high_severity_iocs_open: 2,
    intel_items: comparison(30, 30), documents_processed: comparison(5, 8), knowledge_added: comparison(2, 0),
    reports_delivered: comparison(1, 0), job_success_rate: 90, integration_readiness: null, sensor_coverage: 71.4,
    users: { total: 4, active: 3, engaged: 2 }, activity_events: comparison(100, 50),
  },
  trends: { iocs: series(1), intel: series(2), documents: series(0), reports: series(0), activity: series(4) },
  portfolio: { health: { green: 2, yellow: 0, red: 1 }, projects: [{ id: 1, name: "Ransomware IR", customer: "Retail", health: "red", progress: 20, risks: 2, issues: 0, open_actions: 1 }] },
  risk_register: [{ project_id: 1, project: "Ransomware IR", customer: "Retail", risk: "Log source delay", severity: "high", health: "red" }],
  coverage: { total: 14, covered: 10, coverage_pct: 71.4, active_sensors: 4, gaps: ["Impact"], tactics: [{ tactic: "Initial Access", count: 2, sensors: ["NGFW", "Zeek"] }, { tactic: "Impact", count: 0, sensors: [] }] },
  integrations: { total: 0, connected: 0, attention: 0 },
  feature_expiry: [{ key: "module.reports", expires_at: "2026-09-19T00:00:00+00:00", days_left: 10 }],
  backup: { count: 0, last_backup_at: null, last_backup_bytes: 0 },
  attention: [{ severity: "high", title: "1 investigation(s) in red health", detail: "Review blockers.", link: "/data?tab=projects" }],
};

const technicalPayload = {
  generated_at: "2026-09-09T12:00:00+00:00",
  period: { days: 7, since: "2026-09-02T12:00:00+00:00", until: "2026-09-09T12:00:00+00:00" },
  iocs: { total: 6, by_type: { ipv4: 4, domain: 2 }, by_severity: { high: 2 }, by_confidence: { medium: 6 }, false_positives: 1, fp_ratio: 16.7, new_24h: 2, new_period: 5, expiring_30d: 1, expired: 1, by_status: { active: 5, expired: 1 }, watchlist: 2, avg_score: 72, multi_source: 1, top_sources: [{ name: "ThreatFox", count: 4 }], recent_high: [{ id: 1, value: "10.0.0.1", ioc_type: "ipv4", severity: "high", source: "ThreatFox", created_at: "2026-09-09T11:00:00+00:00" }] },
  intel: { items_24h: 1, items_period: 1, unread: 3, saved: 0, avg_relevance: 0.8, by_category: { Malware: 1 }, by_source: { "Feed A": 1 }, sources: [{ id: 1, name: "Feed A", kind: "rss", enabled: true, interval_minutes: 60, trust_score: 0.7, failure_count: 0, last_success_at: "2026-09-09T11:30:00+00:00", last_error: "", status: "healthy" }], source_status: { healthy: 1, stale: 0, failing: 0, never_run: 0, disabled: 0 } },
  jobs: { total: 4, completed: 3, failed: 1, success_rate: 75, avg_duration_s: 90, p95_duration_s: 90, by_kind: { intelligence: { completed: 3, failed: 1 } }, failed_24h: 1, queue: { pending: 0, running: 0 }, scheduler: [{ id: "daily_backup", name: "_daily_backup", trigger: "cron[hour='2']", next_run_time: "2026-09-10T02:00:00+00:00" }], recent_failures: [{ id: 9, name: "job-0", kind: "intelligence", error: "boom", attempts: 1, created_at: "2026-09-08T12:00:00+00:00" }], notifications_by_status: {} },
  integrations: { connections: [{ id: 1, name: "Jira Cloud", provider: "atlassian", products: ["jira"], enabled: true, status: "connected", last_success_at: "2026-09-09T11:00:00+00:00", last_test_at: null, error_code: "", error_summary: "" }], status_counts: { connected: 1 }, history: { total: 2, success: 1, failed: 1, success_rate: 50, avg_duration_ms: 2625, p95_duration_ms: 5000, by_operation: { search: { success: 1, failed: 1 } }, top_errors: [{ code: "timeout", count: 1 }] }, chat: { turns: 0, failed: 0, error_rate: null, avg_duration_ms: null, by_provider: {} } },
  telemetry: { sensors_total: 2, by_category: { firewall: 1, ids: 1 }, by_status: { active: 1, deprecated: 1 }, by_criticality: { medium: 2 }, log_sources: 2, eps_total: 1700, retention_avg_days: 135, without_siem_index: [{ sensor: "Palo Alto NGFW", log_source: "Threat" }], documents_by_kind: { runbook: 1 }, sensors_without_playbook: ["Palo Alto NGFW"], sensors_without_runbook: [], confluence_published: 0, coverage: { total: 14, covered: 3, coverage_pct: 21.4, active_sensors: 1, gaps: [], tactics: [{ tactic: "Initial Access", count: 1, sensors: ["Palo Alto NGFW"] }] }, eps_by_sensor: [{ sensor: "Palo Alto NGFW", eps: 1700 }] },
  api: { requests: 10, writes: 2, errors: 2, error_rate: 20, p50_ms: 60, p95_ms: 110, max_ms: 110, status_classes: { "2xx": 8, "3xx": 0, "4xx": 0, "5xx": 2 }, by_module: [{ module: "data", requests: 10, errors: 2, error_rate: 20, p95_ms: 110 }], slowest: [{ action: "GET /api/iocs", count: 10, p95_ms: 110 }], active_users: 2, hourly: Array.from({ length: 24 }, (_, i) => ({ hour: `2026-09-08T${String(i).padStart(2, "0")}:00:00+00:00`, count: i % 3, errors: i % 7 === 0 ? 1 : 0 })) },
  storage: { database_bytes: 876544, uploads_bytes: 0, reports_bytes: 0, exports_bytes: 0, backups_bytes: 0, backup: { count: 0, last_backup_at: null, last_backup_bytes: 0 }, documents_total: 1, documents_by_source: { file: 1 }, knowledge_by_type: { note: 2 }, token_estimate_total: 1200, analyses_by_kind: {}, analysis_tokens_total: 0, token_mappings: 4, sensitive_patterns_enabled: 3, reports_by_status: { final: 2 } },
  anomalies: { open: 1, by_kind: { silent_sensor: 1 }, samples_24h: 4, items: [{ id: 7, kind: "silent_sensor", severity: "high", title: "Silent sensor: NGFW / Traffic", detail: "Observed 0 EPS against a 100 EPS baseline.", status: "open" }] },
};

const overviewPayload = {
  counts: { active_projects: 1, documents: 1, knowledge: 2, iocs: 6, jobs_running: 0, jobs_failed: 0 },
  integration_health: { connected: 1, total: 1, attention: 0, chats: 0, items: [] },
  feature_health: { active: 10, unavailable: 0, expiring_soon: [] },
  user_summary: { total: 2, active: 2 },
  recent_activity: [], recent_iocs: [], active_projects: [], failed_jobs: [], recent_jobs: [],
};

function accessFor(features: Record<string, boolean>): AccessState {
  return {
    user: { id: 1, username: "admin", display_name: "Admin", tenant_id: "default", role: "admin" },
    modules: ["dashboard"],
    features: Object.fromEntries(Object.entries(features).map(([key, active]) => [key, { enabled: active, active, status: active ? "active" : "disabled" }])),
    module_catalog: [],
  };
}

function renderAt(path: string, access: AccessState) {
  return render(<MemoryRouter initialEntries={[path]}><ToastProvider><AccessProvider value={access}><Dashboard /></AccessProvider></ToastProvider></MemoryRouter>);
}

afterEach(cleanup);
beforeEach(() => {
  vi.mocked(api.get).mockReset();
  vi.mocked(api.get).mockImplementation(async (path: string) => {
    if (path.startsWith("/api/dashboard/executive")) return executivePayload;
    if (path.startsWith("/api/dashboard/technical")) return technicalPayload;
    return overviewPayload;
  });
});

describe("dashboard views", () => {
  it("renders the executive view with posture, KPI deltas and attention items", async () => {
    renderAt("/?view=executive", accessFor({ "dashboard.executive": true, "dashboard.technical": true }));
    await waitFor(() => expect(screen.getByText("Executive dashboard")).toBeInTheDocument());
    expect(api.get).toHaveBeenCalledWith("/api/dashboard/executive?days=30");
    expect(screen.getByLabelText("Posture score 72 of 100")).toBeInTheDocument();
    expect(screen.getByText("New IoCs")).toBeInTheDocument();
    expect(screen.getByText("▲ 8 (+200%)")).toBeInTheDocument();
    expect(screen.getByText("1 investigation(s) in red health")).toBeInTheDocument();
    expect(screen.getByText("Log source delay")).toBeInTheDocument();
    expect(screen.getByText("module.reports")).toBeInTheDocument();
    expect(screen.getByText("Download brief (.md)")).toBeInTheDocument();
    expect(screen.getByText("Download PDF")).toBeInTheDocument();
    expect(screen.getByText("Publish to Confluence")).toBeInTheDocument();
  });

  it("renders the technical view with pipeline, integration and API analytics", async () => {
    renderAt("/?view=technical&days=1", accessFor({ "dashboard.executive": true, "dashboard.technical": true }));
    await waitFor(() => expect(screen.getByText("Technical dashboard")).toBeInTheDocument());
    expect(api.get).toHaveBeenCalledWith("/api/dashboard/technical?days=1");
    expect(screen.getByText("API error rate")).toBeInTheDocument();
    expect(screen.getAllByText("Feed A").length).toBeGreaterThanOrEqual(2); // source table + yield-by-source bars
    expect(screen.getByText("Jira Cloud")).toBeInTheDocument();
    expect(screen.getByText("daily_backup")).toBeInTheDocument();
    expect(screen.getByText("1 log source(s) without a SIEM index")).toBeInTheDocument();
    expect(screen.getByText("Open anomalies")).toBeInTheDocument();
    expect(screen.getByText("Silent sensor: NGFW / Traffic")).toBeInTheDocument();
    expect(screen.getByText("GET /api/iocs")).toBeInTheDocument();
  });

  it("hides views whose feature policy is inactive and falls back to the overview", async () => {
    renderAt("/?view=executive", accessFor({ "dashboard.executive": false, "dashboard.technical": true }));
    await waitFor(() => expect(screen.getByText(/Welcome back/)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Executive" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Technical" })).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalledWith(expect.stringContaining("/api/dashboard/executive"));
  });
});
