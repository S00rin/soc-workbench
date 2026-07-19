import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAccess } from "../access";
import { Loading, healthBadge, statusBadge, timeAgo } from "../lib";

const QUICK = [
  { label: "Ask integrations", icon: "AI", to: "/integrations?tab=chat" },
  { label: "Upload & analyze", icon: "+", to: "/data?tab=process" },
  { label: "Review IoCs", icon: "IO", to: "/data?tab=iocs" },
  { label: "Integration health", icon: "IN", to: "/integrations?tab=atlassian" },
  { label: "View operations", icon: "OP", to: "/operations" },
];

export default function Dashboard() {
  const access = useAccess();
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const nav = useNavigate();
  useEffect(() => { api.get("/api/dashboard").then(setData).catch(error => setErr(error.message)); }, []);
  if (err) return <div className="card badge red" style={{ display: "block" }}>{err}</div>;
  if (!data) return <Loading />;
  const c = data.counts;
  const stats = [
    { label: "Active Projects", num: c.active_projects, to: "/data?tab=projects" },
    { label: "Documents", num: c.documents, to: "/data?tab=process" },
    { label: "Knowledge", num: c.knowledge, to: "/data?tab=knowledge" },
    { label: "IoCs", num: c.iocs, to: "/data?tab=iocs" },
    { label: "Connected", num: data.integration_health.connected, to: "/integrations" },
    { label: "Prompt Chats", num: data.integration_health.chats, to: "/integrations?tab=chat" },
    { label: "Jobs Running", num: c.jobs_running, to: "/operations" },
    { label: "Needs Attention", num: c.jobs_failed + data.integration_health.attention, to: "/operations", danger: c.jobs_failed + data.integration_health.attention > 0 },
  ];
  return <>
    <div className="dashboard-hero mb"><div><span className="eyebrow">SOORIN SECURITY OPERATIONS</span><h1>Welcome back, {access.user.display_name || access.user.username}</h1><p>Your live operational picture across data, connectors, automation and access policies.</p></div><img src="/brand/soorin-wordmark.png" alt="Soorin" /></div>
    <div className="grid cols-4 mb">{stats.map(item => <button key={item.label} className={`stat stat-button ${item.danger ? "danger" : ""}`} onClick={() => nav(item.to)}><div className="num">{item.num ?? 0}</div><div className="label">{item.label}</div></button>)}</div>
    <div className="dashboard-layout mb">
      <div className="card operational-pulse"><div className="card-head"><div><h3>Operational pulse</h3><span className="faint">Live product health</span></div><span className={`badge ${data.integration_health.attention ? "yellow" : "green"}`}>{data.integration_health.attention ? "Review needed" : "Healthy"}</span></div>
        <Pulse label="Integration connections" value={data.integration_health.connected} total={Math.max(data.integration_health.total, 1)} />
        <Pulse label="Available features" value={data.feature_health.active} total={Math.max(data.feature_health.active + data.feature_health.unavailable, 1)} />
        <Pulse label="Active users" value={data.user_summary.active} total={Math.max(data.user_summary.total, 1)} />
        {data.feature_health.expiring_soon?.length > 0 && <div className="expiry-callout"><b>{data.feature_health.expiring_soon.length} feature(s) expire within 30 days</b><button className="btn-sm" onClick={() => nav("/admin/access")}>Review policies</button></div>}
      </div>
      <div className="card"><div className="card-head"><h3>Quick actions</h3></div><div className="quick-grid">{QUICK.map(item => <button key={item.label} onClick={() => nav(item.to)}><span>{item.icon}</span><b>{item.label}</b></button>)}</div></div>
    </div>
    <div className="grid cols-2">
      <Panel title="Integration health" empty="No integrations configured." rows={data.integration_health.items} render={(row: any) => <><div><b>{row.name}</b><span className="meta">{row.provider}</span></div><span className={`badge ${row.error_code ? "red" : row.last_success_at ? "green" : "yellow"}`}>{row.error_code ? "Attention" : row.last_success_at ? "Connected" : "Not tested"}</span></>} />
      <Panel title="Recent activity" empty="No user activity recorded yet." rows={data.recent_activity} render={(row: any) => <><div><b>{row.actor}</b><span className="meta">{row.module} · {row.action}</span></div><div className="row"><span className={`badge ${row.status_code < 400 ? "green" : "red"}`}>{row.status_code}</span><span className="meta">{timeAgo(row.created_at)}</span></div></>} />
      <Panel title="New IoCs" empty="No IoCs stored." rows={data.recent_iocs} render={(row: any) => <><span className="mono">{row.value}</span><span className="badge">{row.ioc_type}</span></>} />
      <Panel title="Active projects" empty="No active projects." rows={data.active_projects} render={(row: any) => <><div><b>{row.name}</b><span className="meta">{row.customer}</span></div>{healthBadge(row.health)}</>} />
      <Panel title="Failed jobs" empty="No job failures." rows={data.failed_jobs} render={(row: any) => <><span>{row.name}</span><span className="meta" title={row.error}>{(row.error || "").slice(0, 55)}</span></>} />
      <Panel title="Recent jobs" empty="No jobs run yet." rows={data.recent_jobs} render={(row: any) => <><span>{row.name}</span>{statusBadge(row.status)}</>} />
    </div>
  </>;
}

function Pulse({ label, value, total }: { label: string; value: number; total: number }) {
  const percent = Math.max(0, Math.min(100, Math.round(value / total * 100)));
  return <div className="pulse-row"><div className="row"><span>{label}</span><span className="spacer" /><b>{value}/{total}</b></div><div className="progress-bar"><span style={{ width: `${percent}%` }} /></div></div>;
}

function Panel({ title, rows, render, empty }: any) {
  return <div className="card"><div className="card-head"><h3>{title}</h3></div><div className="list">{(!rows || rows.length === 0) && <div className="empty">{empty}</div>}{rows?.map((row: any, index: number) => <div className="list-row" key={row.id || index}>{render(row)}</div>)}</div></div>;
}
