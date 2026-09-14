import { useNavigate } from "react-router-dom";
import { api } from "../../api";
import { Loading, timeAgo, useToast } from "../../lib";
import {
  BarList, Empty, HourlyBars, KeyValue, Metric, Section, SeverityBadge, StatusBadge, TacticGrid,
  fmtBytes, fmtDate, fmtMs, fmtNum, fmtPct, toneFor, useLiveData,
} from "./shared";

const PERIODS = [1, 7, 30];

export default function Technical({ days, onDays, refreshMs }: { days: number; onDays: (value: number) => void; refreshMs: number }) {
  const nav = useNavigate();
  const toast = useToast();
  const { data, err, loading, refresh, updatedAt } = useLiveData(`/api/dashboard/technical?days=${days}`, refreshMs);
  if (err) return <div className="card badge red" style={{ display: "block" }}>{err}</div>;
  if (!data) return <Loading label="Computing technical metrics…" />;
  const { iocs, intel, jobs, integrations, telemetry, api: apiStats, storage, anomalies } = data;

  async function ackAnomaly(id: number, action: "ack" | "resolve") {
    try {
      await api.post(`/api/anomalies/${id}/${action}`);
      toast(action === "ack" ? "Acknowledged" : "Resolved", "ok");
      refresh();
    } catch (error: any) { toast(error.message, "error"); }
  }
  async function runDetection() {
    try {
      const result = await api.post("/api/anomalies/run");
      toast(result.skipped ? "Detection is disabled" : `Opened ${result.opened} alert(s)`, "ok");
      refresh();
    } catch (error: any) { toast(error.message, "error"); }
  }

  return <>
    <div className="dash-toolbar mb">
      <div><h1>Technical dashboard</h1><p className="dim">Pipeline, integration, telemetry and platform health for the last {days === 1 ? "24 hours" : `${days} days`}. {updatedAt && <span className="faint">Updated {updatedAt.toLocaleTimeString()}</span>}</p></div>
      <div className="row">
        <div className="pill-toggle" role="group" aria-label="Analysis window">{PERIODS.map(p => <button key={p} className={p === days ? "active" : ""} onClick={() => onDays(p)}>{p === 1 ? "24h" : `${p}d`}</button>)}</div>
        <button className="btn-sm" onClick={refresh} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button>
      </div>
    </div>

    <div className="kpi-strip mb">
      <Metric label="API requests" value={fmtNum(apiStats.requests)} hint={`${fmtNum(apiStats.writes)} writes · ${apiStats.active_users} users`} />
      <Metric label="API error rate" value={fmtPct(apiStats.error_rate)} hint={`${apiStats.status_classes["4xx"]} 4xx · ${apiStats.status_classes["5xx"]} 5xx`} tone={toneFor(apiStats.error_rate, 1, 5, true)} />
      <Metric label="p95 latency" value={fmtMs(apiStats.p95_ms)} hint={`p50 ${fmtMs(apiStats.p50_ms)}`} tone={toneFor(apiStats.p95_ms, 500, 2000, true)} />
      <Metric label="Job success" value={fmtPct(jobs.success_rate)} hint={`${jobs.failed_24h} failed in 24h`} tone={toneFor(jobs.success_rate, 95, 80)} onClick={() => nav("/operations?tab=jobs")} />
      <Metric label="Job queue" value={`${jobs.queue.running} / ${jobs.queue.pending}`} hint="running / pending" />
      <Metric label="IoCs (24h)" value={fmtNum(iocs.new_24h)} hint={`${fmtNum(iocs.total)} total · ${iocs.multi_source} multi-source`} onClick={() => nav("/data?tab=iocs")} />
      <Metric label="Intel (24h)" value={fmtNum(intel.items_24h)} hint={`${intel.unread} unread`} onClick={() => nav("/intelligence?tab=intel")} />
      <Metric label="Telemetry EPS" value={fmtNum(telemetry.eps_total)} hint={`${telemetry.log_sources} log sources · ${telemetry.sensors_total} sensors`} onClick={() => nav("/sensors")} />
      <Metric label="Open anomalies" value={fmtNum(anomalies?.open || 0)} hint={Object.entries(anomalies?.by_kind || {}).map(([k, v]) => `${k} ${v}`).join(" · ") || "silent-sensor / feed yield"} tone={(anomalies?.open || 0) > 0 ? "red" : "green"} />
    </div>

    <Section title="Silent-sensor & feed anomalies" subtitle={`${anomalies?.samples_24h || 0} sample(s) in 24h · EPS and yield vs rolling baselines`} className="mb" action={<button className="btn-sm" onClick={runDetection}>Run detection</button>}>
      {!anomalies?.items?.length ? <Empty>No open silent-sensor or feed-anomaly alerts.</Empty> : <div className="list">{anomalies.items.map((item: any) => <div className="list-row attention-row" key={item.id}>
        <div><div className="row"><SeverityBadge level={item.severity} /><span className="badge">{item.kind.replace("_", " ")}</span><b>{item.title}</b></div><span className="meta">{item.detail}</span></div>
        <div className="row"><button className="btn-sm btn-ghost" onClick={() => ackAnomaly(item.id, "ack")}>Ack</button><button className="btn-sm" onClick={() => ackAnomaly(item.id, "resolve")}>Resolve</button></div>
      </div>)}</div>}
    </Section>

    <div className="grid cols-2 mb">
      <Section title="IoC analytics" subtitle="Indicator inventory and hygiene" action={<button className="btn-sm btn-ghost" onClick={() => nav("/data?tab=iocs")}>Open IoCs</button>}>
        <div className="two-col">
          <div><h4>By type</h4><BarList data={iocs.by_type} /></div>
          <div><h4>By severity</h4><BarList data={iocs.by_severity} color="var(--red)" /></div>
        </div>
        <KeyValue rows={[
          ["False positives", `${iocs.false_positives} (${fmtPct(iocs.fp_ratio)})`],
          ["Expired / expiring 30d", `${iocs.expired} / ${iocs.expiring_30d}`],
          ["Watchlist / avg score", `${fmtNum(iocs.watchlist || 0)} / ${iocs.avg_score ?? "—"}`],
          ["Lifecycle", Object.entries(iocs.by_status || {}).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"],
          ["New in period", fmtNum(iocs.new_period)],
          ["Confidence", Object.entries(iocs.by_confidence).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"],
        ]} />
        <h4>Top sources</h4><BarList data={iocs.top_sources} color="var(--purple)" />
        {iocs.recent_high.length > 0 && <><h4>Latest high / critical</h4><div className="list">{iocs.recent_high.map((row: any) => <div className="list-row" key={row.id}><span className="mono">{row.value}</span><div className="row"><span className="badge">{row.ioc_type}</span><SeverityBadge level={row.severity} /><span className="meta">{timeAgo(row.created_at)}</span></div></div>)}</div></>}
      </Section>

      <Section title="Intelligence pipeline" subtitle="Collection sources and yield" action={<button className="btn-sm btn-ghost" onClick={() => nav("/intelligence?tab=automation")}>Automation</button>}>
        <div className="status-chips">{Object.entries(intel.source_status).map(([status, count]) => <span key={status} className="chip"><StatusBadge status={status} /> {count as number}</span>)}</div>
        {intel.sources.length === 0 ? <Empty>No intelligence sources configured.</Empty> : <table className="data compact"><thead><tr><th>Source</th><th>Kind</th><th>Status</th><th>Last success</th><th>Fail</th></tr></thead><tbody>
          {intel.sources.map((s: any) => <tr key={`${s.kind}-${s.id}`} title={s.last_error}><td><b>{s.name}</b></td><td className="dim">{s.kind}</td><td><StatusBadge status={s.status} /></td><td className="dim">{s.last_success_at ? timeAgo(s.last_success_at) : "never"}</td><td>{s.failure_count}</td></tr>)}
        </tbody></table>}
        <div className="two-col mt">
          <div><h4>Items by category</h4><BarList data={intel.by_category} /></div>
          <div><h4>Items by source</h4><BarList data={intel.by_source} color="var(--purple)" /></div>
        </div>
        <KeyValue rows={[["Items in period", fmtNum(intel.items_period)], ["Average relevance", intel.avg_relevance ?? "—"], ["Saved", fmtNum(intel.saved)], ["Unread", fmtNum(intel.unread)]]} />
      </Section>
    </div>

    <div className="grid cols-2 mb">
      <Section title="Background jobs & scheduler" subtitle={`${jobs.total} job(s) in period`} action={<button className="btn-sm btn-ghost" onClick={() => nav("/operations?tab=jobs")}>Operations</button>}>
        <KeyValue rows={[["Success rate", fmtPct(jobs.success_rate)], ["Avg / p95 duration", `${jobs.avg_duration_s ?? "—"} s / ${jobs.p95_duration_s ?? "—"} s`], ["Failed (24h)", fmtNum(jobs.failed_24h)], ["Queue", `${jobs.queue.running} running · ${jobs.queue.pending} pending`]]} />
        {Object.keys(jobs.by_kind).length > 0 && <><h4>Status by kind</h4><table className="data compact"><thead><tr><th>Kind</th><th>Completed</th><th>Failed</th><th>Running</th><th>Pending</th></tr></thead><tbody>
          {Object.entries(jobs.by_kind).map(([kind, counts]: [string, any]) => <tr key={kind}><td><b>{kind}</b></td><td>{counts.completed || 0}</td><td className={counts.failed ? "text-red" : ""}>{counts.failed || 0}</td><td>{counts.running || 0}</td><td>{counts.pending || 0}</td></tr>)}
        </tbody></table></>}
        <h4>Scheduled tasks</h4>
        {jobs.scheduler.length === 0 ? <Empty>Scheduler is not running.</Empty> : <div className="list">{jobs.scheduler.map((s: any) => <div className="list-row" key={s.id}><div><b>{s.id}</b><span className="meta mono">{s.trigger}</span></div><span className="meta">next {fmtDate(s.next_run_time)}</span></div>)}</div>}
        {jobs.recent_failures.length > 0 && <><h4>Recent failures</h4><div className="list">{jobs.recent_failures.map((j: any) => <div className="list-row" key={j.id}><div><b>{j.name}</b><span className="meta">{j.kind} · {j.attempts} attempt(s) · {timeAgo(j.created_at)}</span></div><span className="meta error-text" title={j.error}>{j.error.slice(0, 60)}</span></div>)}</div></>}
      </Section>

      <Section title="Integrations" subtitle="Connector state and operation history" action={<button className="btn-sm btn-ghost" onClick={() => nav("/integrations")}>Analyzer Hub</button>}>
        {integrations.connections.length === 0 ? <Empty>No connections configured.</Empty> : <table className="data compact"><thead><tr><th>Connection</th><th>Provider</th><th>Status</th><th>Last success</th></tr></thead><tbody>
          {integrations.connections.map((c: any) => <tr key={`${c.provider}-${c.id}`} title={c.error_summary}><td><b>{c.name}</b></td><td className="dim">{c.products.join(", ")}</td><td><StatusBadge status={c.status} />{c.error_code && <span className="meta"> {c.error_code}</span>}</td><td className="dim">{c.last_success_at ? timeAgo(c.last_success_at) : "never"}</td></tr>)}
        </tbody></table>}
        <h4>Operation history</h4>
        <KeyValue rows={[["Operations", `${integrations.history.total} (${fmtPct(integrations.history.success_rate)} ok)`], ["Avg / p95 duration", `${fmtMs(integrations.history.avg_duration_ms)} / ${fmtMs(integrations.history.p95_duration_ms)}`], ["Chat turns", `${integrations.chat.turns} (${fmtPct(integrations.chat.error_rate)} failed)`], ["Chat avg latency", fmtMs(integrations.chat.avg_duration_ms)]]} />
        <div className="two-col">
          <div><h4>By operation</h4><BarList data={Object.fromEntries(Object.entries(integrations.history.by_operation).map(([k, v]: [string, any]) => [k, Object.values(v as Record<string, number>).reduce((a: number, b: number) => a + b, 0)]))} /></div>
          <div><h4>Top error codes</h4><BarList data={integrations.history.top_errors.map((e: any) => ({ name: e.code, count: e.count }))} color="var(--red)" /></div>
        </div>
      </Section>
    </div>

    <div className="grid cols-2 mb">
      <Section title="Telemetry & detection coverage" subtitle={`${telemetry.sensors_total} sensor(s), ${telemetry.log_sources} log source(s)`} action={<button className="btn-sm btn-ghost" onClick={() => nav("/sensors")}>Sensor library</button>}>
        <TacticGrid tactics={telemetry.coverage.tactics} />
        <div className="two-col mt">
          <div><h4>Sensors by category</h4><BarList data={telemetry.by_category} /></div>
          <div><h4>EPS by sensor</h4><BarList data={telemetry.eps_by_sensor.map((e: any) => ({ name: e.sensor, count: e.eps }))} color="var(--green)" /></div>
        </div>
        <KeyValue rows={[
          ["Status", Object.entries(telemetry.by_status).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"],
          ["Criticality", Object.entries(telemetry.by_criticality).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"],
          ["Avg retention", telemetry.retention_avg_days ? `${telemetry.retention_avg_days} days` : "—"],
          ["Published to Confluence", fmtNum(telemetry.confluence_published)],
        ]} />
        {(telemetry.without_siem_index.length > 0 || telemetry.sensors_without_playbook.length > 0) && <div className="gap-callouts">
          {telemetry.without_siem_index.length > 0 && <div className="expiry-callout"><div><b>{telemetry.without_siem_index.length} log source(s) without a SIEM index</b><span className="meta">{telemetry.without_siem_index.map((g: any) => `${g.sensor} › ${g.log_source}`).join(", ")}</span></div></div>}
          {telemetry.sensors_without_playbook.length > 0 && <div className="expiry-callout"><div><b>{telemetry.sensors_without_playbook.length} sensor(s) without a playbook</b><span className="meta">{telemetry.sensors_without_playbook.join(", ")}</span></div></div>}
        </div>}
      </Section>

      <Section title="API performance" subtitle="From the activity log · errors in red">
        <HourlyBars points={apiStats.hourly} />
        <div className="row faint sparkline-axis"><span>{apiStats.hourly[0]?.hour.slice(5, 16).replace("T", " ")}</span><span className="spacer" /><span>now</span></div>
        <KeyValue rows={[["Requests", fmtNum(apiStats.requests)], ["Errors", `${apiStats.errors} (${fmtPct(apiStats.error_rate)})`], ["p50 / p95 / max", `${fmtMs(apiStats.p50_ms)} / ${fmtMs(apiStats.p95_ms)} / ${fmtMs(apiStats.max_ms)}`], ["Status classes", Object.entries(apiStats.status_classes).map(([k, v]) => `${k} ${v}`).join(" · ")]]} />
        {apiStats.by_module.length > 0 && <><h4>By module</h4><table className="data compact"><thead><tr><th>Module</th><th>Requests</th><th>Errors</th><th>p95</th></tr></thead><tbody>
          {apiStats.by_module.map((m: any) => <tr key={m.module}><td><b>{m.module}</b></td><td>{fmtNum(m.requests)}</td><td className={m.errors ? "text-red" : ""}>{m.errors} ({fmtPct(m.error_rate)})</td><td className="mono">{fmtMs(m.p95_ms)}</td></tr>)}
        </tbody></table></>}
        {apiStats.slowest.length > 0 && <><h4>Slowest endpoints (p95)</h4><BarList data={apiStats.slowest.map((s: any) => ({ name: s.action, count: s.p95_ms || 0 }))} format={v => fmtMs(v)} color="var(--yellow)" /></>}
      </Section>
    </div>

    <div className="grid cols-3">
      <Section title="Storage" subtitle="Data directory footprint">
        <BarList data={{ Database: storage.database_bytes, Uploads: storage.uploads_bytes, Reports: storage.reports_bytes, Exports: storage.exports_bytes, Backups: storage.backups_bytes }} format={fmtBytes} />
        <KeyValue rows={[["Last backup", fmtDate(storage.backup.last_backup_at)], ["Backups kept", `${storage.backup.count} (${fmtBytes(storage.backup.last_backup_bytes)} latest)`]]} />
      </Section>
      <Section title="Content inventory" subtitle="Documents, knowledge and analyses">
        <div className="two-col">
          <div><h4>Documents by source</h4><BarList data={storage.documents_by_source} /></div>
          <div><h4>Analyses by kind</h4><BarList data={storage.analyses_by_kind} color="var(--purple)" /></div>
        </div>
        <KeyValue rows={[["Documents", fmtNum(storage.documents_total)], ["Reports", Object.entries(storage.reports_by_status).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"]]} />
      </Section>
      <Section title="LLM & data protection" subtitle="Token budget and tokenization">
        <KeyValue rows={[
          ["Document tokens (est.)", fmtNum(storage.token_estimate_total)],
          ["Analysis tokens (est.)", fmtNum(storage.analysis_tokens_total)],
          ["Protected token mappings", fmtNum(storage.token_mappings)],
          ["Sensitive patterns enabled", fmtNum(storage.sensitive_patterns_enabled)],
          ["Knowledge by type", Object.entries(storage.knowledge_by_type).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"],
        ]} />
      </Section>
    </div>
  </>;
}
