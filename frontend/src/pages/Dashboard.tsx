import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Loading, healthBadge, statusBadge, timeAgo } from "../lib";

const QUICK = [
  { label: "Upload & analyze", icon: "⇪", to: "/process" },
  { label: "Add KB item", icon: "❏", to: "/knowledge?new=1" },
  { label: "Extract IoCs", icon: "⌖", to: "/iocs" },
  { label: "New project", icon: "◈", to: "/projects?new=1" },
  { label: "View jobs", icon: "⚙", to: "/jobs" },
  { label: "Settings", icon: "⚙", to: "/settings" },
];

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const nav = useNavigate();

  useEffect(() => {
    api.get("/api/dashboard").then(setData).catch((e) => setErr(e.message));
  }, []);

  if (err) return <div className="card badge red" style={{ display: "block" }}>{err}</div>;
  if (!data) return <Loading />;

  const c = data.counts;
  const stats = [
    { label: "Active Projects", num: c.projects, to: "/projects" },
    { label: "Documents", num: c.documents, to: "/process" },
    { label: "Knowledge Items", num: c.knowledge, to: "/knowledge" },
    { label: "IoCs", num: c.iocs, to: "/iocs" },
    { label: "Reports", num: c.reports },
    { label: "Intel Items", num: c.intel },
    { label: "Jobs Running", num: c.jobs_running, to: "/jobs" },
    { label: "Failed Jobs", num: c.jobs_failed, to: "/jobs", danger: c.jobs_failed > 0 },
  ];

  return (
    <>
      <div className="grid cols-4 mb">
        {stats.map((s) => (
          <div
            key={s.label}
            className={`stat ${s.danger ? "danger" : ""}`}
            style={{ cursor: s.to ? "pointer" : "default" }}
            onClick={() => s.to && nav(s.to)}
          >
            <div className="num">{s.num}</div>
            <div className="label">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="card mb">
        <div className="card-head"><h3>Quick actions</h3></div>
        <div className="row">
          {QUICK.map((q) => (
            <button key={q.label} onClick={() => nav(q.to)}>
              <span>{q.icon}</span> {q.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid cols-2">
        <Panel title="Recent Documents" empty="No processed documents yet." to="/process" nav={nav}
          rows={data.recent_documents} render={(d: any) => (
            <>
              <span>{d.title}</span>
              <span className="meta">{d.source_type} · {timeAgo(d.created_at)}</span>
            </>
          )} />
        <Panel title="Recent Knowledge" empty="Knowledge base is empty." to="/knowledge" nav={nav}
          rows={data.recent_knowledge} render={(k: any) => (
            <>
              <span>{k.title}</span>
              <span className="meta">{k.item_type} · {timeAgo(k.updated_at)}</span>
            </>
          )} />
        <Panel title="New IoCs" empty="No IoCs stored." to="/iocs" nav={nav}
          rows={data.recent_iocs} render={(i: any) => (
            <>
              <span className="mono">{i.value}</span>
              <span className="badge">{i.ioc_type}</span>
            </>
          )} />
        <Panel title="Active Projects" empty="No active projects." to="/projects" nav={nav}
          rows={data.active_projects} render={(p: any) => (
            <>
              <span>{p.name} <span className="dim">{p.customer}</span></span>
              {healthBadge(p.health)}
            </>
          )} />
        <Panel title="Failed jobs / connector errors" empty="No failures. 🎉" to="/jobs" nav={nav}
          rows={data.failed_jobs} render={(j: any) => (
            <>
              <span>{j.name}</span>
              <span className="meta" title={j.error}>{(j.error || "").slice(0, 40)}</span>
            </>
          )} />
        <Panel title="Recent jobs" empty="No jobs run yet." to="/jobs" nav={nav}
          rows={data.recent_jobs} render={(j: any) => (
            <>
              <span>{j.name}</span>
              {statusBadge(j.status)}
            </>
          )} />
      </div>
    </>
  );
}

function Panel({ title, rows, render, empty, to, nav }: any) {
  return (
    <div className="card">
      <div className="card-head">
        <h3>{title}</h3>
        {to && <a onClick={() => nav(to)} style={{ cursor: "pointer", fontSize: 12.5 }}>View all →</a>}
      </div>
      <div className="list">
        {(!rows || rows.length === 0) && <div className="empty">{empty}</div>}
        {rows?.map((r: any, i: number) => (
          <div className="list-row" key={i}>{render(r)}</div>
        ))}
      </div>
    </div>
  );
}
