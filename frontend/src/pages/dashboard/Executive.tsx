import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api";
import { Loading, healthBadge, useToast } from "../../lib";
import {
  BarList, Delta, Donut, Empty, Gauge, KeyValue, Legend, Metric, Section, SeverityBadge, Sparkline, TacticGrid,
  fmtDate, fmtNum, fmtPct, toneFor, useLiveData,
} from "./shared";

const PERIODS = [7, 30, 90];

export default function Executive({ days, onDays, refreshMs }: { days: number; onDays: (value: number) => void; refreshMs: number }) {
  const nav = useNavigate();
  const toast = useToast();
  const [busy, setBusy] = useState("");
  const { data, err, loading, refresh, updatedAt } = useLiveData(`/api/dashboard/executive?days=${days}`, refreshMs);

  async function downloadBrief() {
    setBusy("download");
    try { await api.download(`/api/dashboard/executive/brief?days=${days}`, `executive-brief-${new Date().toISOString().slice(0, 10)}.md`); }
    catch (error: any) { toast(error.message, "error"); }
    finally { setBusy(""); }
  }
  async function downloadPdf() {
    setBusy("pdf");
    try { await api.download(`/api/dashboard/executive/brief.pdf?days=${days}`, `executive-brief-${new Date().toISOString().slice(0, 10)}.pdf`); }
    catch (error: any) { toast(error.message, "error"); }
    finally { setBusy(""); }
  }
  async function saveReport(publish = false) {
    setBusy(publish ? "publish" : "report");
    try {
      const report = await api.post(`/api/dashboard/executive/report?days=${days}&publish=${publish}`);
      if (publish) {
        const url = report.confluence?.url;
        toast(url ? `Published to Confluence` : (report.confluence?.error || `Saved "${report.title}"`), url ? "ok" : "error");
      } else {
        toast(`Saved "${report.title}" to Reports as PDF`, "ok");
      }
    } catch (error: any) { toast(error.message, "error"); }
    finally { setBusy(""); }
  }

  if (err) return <div className="card badge red" style={{ display: "block" }}>{err}</div>;
  if (!data) return <Loading label="Computing executive summary…" />;
  const { kpis, posture, trends, portfolio, coverage } = data;
  const healthSegments = [
    { label: "Green", value: portfolio.health.green, color: "var(--green)" },
    { label: "Yellow", value: portfolio.health.yellow, color: "var(--yellow)" },
    { label: "Red", value: portfolio.health.red, color: "var(--red)" },
  ];

  return <>
    <div className="dash-toolbar mb">
      <div><h1>Executive dashboard</h1><p className="dim">Security posture, delivery KPIs and risks for the last {days} days. {updatedAt && <span className="faint">Updated {updatedAt.toLocaleTimeString()}</span>}</p></div>
      <div className="row">
        <div className="pill-toggle" role="group" aria-label="Reporting period">{PERIODS.map(p => <button key={p} className={p === days ? "active" : ""} onClick={() => onDays(p)}>{p}d</button>)}</div>
        <button className="btn-sm" onClick={refresh} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button>
        <button className="btn-sm" onClick={downloadBrief} disabled={busy !== ""}>Download brief (.md)</button>
        <button className="btn-sm" onClick={downloadPdf} disabled={busy !== ""}>Download PDF</button>
        <button className="btn-sm" onClick={() => saveReport(false)} disabled={busy !== ""}>Save to Reports</button>
        <button className="btn-sm btn-primary" onClick={() => saveReport(true)} disabled={busy !== ""}>Publish to Confluence</button>
      </div>
    </div>

    <div className="exec-top mb">
      <Section title="Security posture" subtitle="Weighted composite of measurable signals" className="posture-card">
        <div className="posture-body">
          <Gauge score={posture.score} grade={posture.grade} />
          <div className="posture-components">{posture.components.map((c: any) => <div key={c.key} className="component-row" title={c.detail}>
            <div className="row"><span>{c.label}</span><span className="spacer" /><span className="faint">{Math.round(c.weight * 100)}%</span><b className={c.score === null ? "faint" : ""}>{c.score === null ? "n/a" : Math.round(c.score)}</b></div>
            <div className="progress-bar"><span className={`tone-${toneFor(c.score, 75, 50)}`} style={{ width: `${c.score ?? 0}%` }} /></div>
          </div>)}</div>
        </div>
      </Section>
      <div className="kpi-grid">
        <Metric label="Active investigations" value={kpis.active_investigations} hint={`${kpis.red_investigations} red · avg progress ${kpis.avg_progress ?? "—"}%`} tone={kpis.red_investigations ? "red" : ""} onClick={() => nav("/data?tab=projects")} />
        <Metric label="New IoCs" value={kpis.iocs_new.value} delta={kpis.iocs_new} hint={`${kpis.high_severity_iocs_open} high/critical active`} onClick={() => nav("/data?tab=iocs")} />
        <Metric label="Intelligence items" value={kpis.intel_items.value} delta={kpis.intel_items} onClick={() => nav("/intelligence?tab=intel")} />
        <Metric label="Documents processed" value={kpis.documents_processed.value} delta={kpis.documents_processed} onClick={() => nav("/data?tab=process")} />
        <Metric label="Reports delivered" value={kpis.reports_delivered.value} delta={kpis.reports_delivered} onClick={() => nav("/reports")} />
        <Metric label="Automation success" value={fmtPct(kpis.job_success_rate)} tone={toneFor(kpis.job_success_rate, 95, 80)} onClick={() => nav("/operations?tab=jobs")} />
        <Metric label="Integration readiness" value={fmtPct(kpis.integration_readiness)} hint={`${data.integrations.connected}/${data.integrations.total} connected`} tone={toneFor(kpis.integration_readiness, 100, 60)} onClick={() => nav("/integrations")} />
        <Metric label="ATT&CK coverage" value={fmtPct(kpis.sensor_coverage)} hint={`${coverage.covered}/${coverage.total} tactics`} tone={toneFor(kpis.sensor_coverage, 70, 40)} onClick={() => nav("/sensors")} />
        <Metric label="Engaged users" value={`${kpis.users.engaged}/${kpis.users.active}`} hint="active accounts used the platform" delta={kpis.activity_events} onClick={() => nav("/admin/audit")} />
      </div>
    </div>

    <Section title="Activity trends" subtitle={`Daily volumes over ${days} days`} className="mb">
      <div className="spark-grid">
        <Sparkline label="IoCs" points={trends.iocs} />
        <Sparkline label="Intelligence" points={trends.intel} color="var(--purple)" />
        <Sparkline label="Documents" points={trends.documents} color="var(--green)" />
        <Sparkline label="Reports" points={trends.reports} color="var(--yellow)" />
        <Sparkline label="User activity" points={trends.activity} color="var(--text-dim)" />
      </div>
    </Section>

    <div className="grid cols-2 mb">
      <Section title="Needs attention" subtitle={`${data.attention.length} item(s) ranked by severity`}>
        {data.attention.length === 0 && <Empty>Nothing requires executive attention.</Empty>}
        <div className="list">{data.attention.map((item: any, index: number) => <div className="list-row attention-row" key={index}>
          <div><div className="row"><SeverityBadge level={item.severity} /><b>{item.title}</b></div><span className="meta">{item.detail}</span></div>
          <button className="btn-sm btn-ghost" onClick={() => nav(item.link)}>Open</button>
        </div>)}</div>
      </Section>
      <Section title="Investigation portfolio" subtitle="Active projects by health">
        <div className="row portfolio-head"><Donut segments={healthSegments} /><Legend items={healthSegments} /></div>
        {portfolio.projects.length === 0 ? <Empty>No active investigations.</Empty> : <table className="data compact"><thead><tr><th>Project</th><th>Customer</th><th>Health</th><th>Progress</th><th>Risks</th></tr></thead><tbody>
          {portfolio.projects.map((p: any) => <tr key={p.id}><td><b>{p.name}</b></td><td className="dim">{p.customer || "—"}</td><td>{healthBadge(p.health)}</td><td><div className="progress-bar small"><span style={{ width: `${p.progress}%` }} /></div></td><td>{p.risks}</td></tr>)}
        </tbody></table>}
      </Section>
    </div>

    <div className="grid cols-2 mb">
      <Section title="Risk register" subtitle="Open risks across active investigations">
        {data.risk_register.length === 0 ? <Empty>No open risks recorded on active projects.</Empty> : <table className="data compact"><thead><tr><th>Severity</th><th>Risk</th><th>Project</th></tr></thead><tbody>
          {data.risk_register.map((r: any, index: number) => <tr key={index}><td><SeverityBadge level={r.severity} /></td><td>{r.risk}</td><td className="dim">{r.project}</td></tr>)}
        </tbody></table>}
      </Section>
      <Section title="Detection coverage" subtitle={`${coverage.covered} of ${coverage.total} MITRE ATT&CK tactics covered by ${coverage.active_sensors} active sensor(s)`} action={<button className="btn-sm btn-ghost" onClick={() => nav("/sensors")}>Sensor library</button>}>
        <TacticGrid tactics={coverage.tactics} />
      </Section>
    </div>

    <div className="grid cols-3">
      <Section title="Governance" subtitle="Feature policies expiring within 30 days">
        {data.feature_expiry.length === 0 ? <Empty>No policies expire within 30 days.</Empty> : <BarList data={Object.fromEntries(data.feature_expiry.map((f: any) => [f.key, f.days_left]))} max={30} format={v => `${v}d`} color="var(--yellow)" />}
      </Section>
      <Section title="Continuity" subtitle="Backups and users">
        <KeyValue rows={[
          ["Last backup", fmtDate(data.backup.last_backup_at)],
          ["Backups kept", fmtNum(data.backup.count)],
          ["User accounts", `${kpis.users.active} active of ${kpis.users.total}`],
          ["Activity events", <span key="a">{fmtNum(kpis.activity_events.value)} <Delta metric={kpis.activity_events} /></span>],
        ]} />
      </Section>
      <Section title="Knowledge growth" subtitle="Curated content added">
        <KeyValue rows={[
          ["Knowledge items", <span key="k">{fmtNum(kpis.knowledge_added.value)} <Delta metric={kpis.knowledge_added} /></span>],
          ["Documents", <span key="d">{fmtNum(kpis.documents_processed.value)} <Delta metric={kpis.documents_processed} /></span>],
          ["Reports", <span key="r">{fmtNum(kpis.reports_delivered.value)} <Delta metric={kpis.reports_delivered} /></span>],
          ["Period", `${data.period.since.slice(0, 10)} → ${data.period.until.slice(0, 10)}`],
        ]} />
      </Section>
    </div>
  </>;
}
