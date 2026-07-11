import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Loading, Modal, healthBadge, statusBadge, timeAgo, useToast } from "../lib";

type Project = {
  id: number;
  name: string;
  customer: string;
  description: string;
  status: string;
  start_date: string;
  end_date: string;
  manager: string;
  tech_owner: string;
  health: string;
  progress: number;
  jira_project: string;
  splunk_env: string;
  notes: string;
  created_at: string;
  updated_at: string;
};

const BLANK = {
  name: "", customer: "", description: "", status: "active", start_date: "", end_date: "",
  manager: "", tech_owner: "", health: "green", progress: 0, jira_project: "", splunk_env: "", notes: "",
};

const STATUSES = ["", "active", "planned", "on_hold", "completed", "archived"];

export default function Projects() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [status, setStatus] = useState("");
  const [editing, setEditing] = useState<any | null>(null);
  const [params, setParams] = useSearchParams();
  const toast = useToast();

  async function load() {
    try {
      const qs = status ? `?status=${status}` : "";
      setProjects(await api.get(`/api/projects${qs}`));
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  useEffect(() => {
    if (params.get("new") === "1") {
      setEditing({ ...BLANK });
      params.delete("new");
      setParams(params, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function remove(p: Project) {
    if (!confirm(`Delete project "${p.name}"?`)) return;
    try {
      await api.del(`/api/projects/${p.id}`);
      toast("Deleted", "ok");
      setProjects((prev) => prev?.filter((x) => x.id !== p.id) ?? null);
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  if (!projects) return <Loading />;

  return (
    <>
      <div className="row mb">
        <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ maxWidth: 180 }}>
          {STATUSES.map((s) => <option key={s} value={s}>{s ? s.replace("_", " ") : "All statuses"}</option>)}
        </select>
        <span className="spacer" />
        <button className="btn-primary btn-sm" onClick={() => setEditing({ ...BLANK })}>+ New project</button>
      </div>

      {projects.length === 0 ? (
        <div className="card"><div className="empty">No projects yet.</div></div>
      ) : (
        <div className="grid cols-2">
          {projects.map((p) => (
            <div className="card" key={p.id}>
              <div className="card-head">
                <div>
                  <h3 style={{ marginBottom: 2 }}>{p.name}</h3>
                  {p.customer && <div className="dim" style={{ fontSize: 12.5 }}>{p.customer}</div>}
                </div>
                <div className="row" style={{ gap: 6 }}>
                  {healthBadge(p.health)}
                  {statusBadge(p.status)}
                </div>
              </div>
              {p.description && <p className="dim" style={{ marginTop: 0, fontSize: 13 }}>{p.description.slice(0, 160)}</p>}
              <div className="progress-bar"><span style={{ width: `${Math.min(100, p.progress)}%` }} /></div>
              <div className="row" style={{ justifyContent: "space-between", marginTop: 10 }}>
                <span className="faint" style={{ fontSize: 12 }}>
                  {p.progress}% · updated {timeAgo(p.updated_at)}
                </span>
                <span className="row" style={{ gap: 6 }}>
                  <button className="btn-sm" onClick={() => setEditing({ ...p })}>Edit</button>
                  <button className="btn-sm btn-danger" onClick={() => remove(p)}>Delete</button>
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && (
        <ProjectModal
          initial={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
    </>
  );
}

function ProjectModal({ initial, onClose, onSaved }: { initial: any; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<any>(initial);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));
  const isEdit = !!initial.id;

  async function save() {
    if (!f.name.trim()) return toast("Name is required", "error");
    setBusy(true);
    const body = {
      name: f.name, customer: f.customer, description: f.description, status: f.status,
      start_date: f.start_date, end_date: f.end_date, manager: f.manager, tech_owner: f.tech_owner,
      health: f.health, progress: Number(f.progress) || 0, jira_project: f.jira_project,
      splunk_env: f.splunk_env, notes: f.notes,
    };
    try {
      if (isEdit) await api.put(`/api/projects/${f.id}`, body);
      else await api.post("/api/projects", body);
      toast(isEdit ? "Updated" : "Created", "ok");
      onSaved();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={isEdit ? "Edit project" : "New project"}
      onClose={onClose}
      wide
      footer={
        <>
          <button className="btn-sm" onClick={onClose}>Cancel</button>
          <button className="btn-primary btn-sm" onClick={save} disabled={busy}>{busy ? <span className="spin" /> : "Save"}</button>
        </>
      }
    >
      <div className="field-row">
        <div><label>Name</label><input value={f.name} onChange={(e) => set("name", e.target.value)} autoFocus /></div>
        <div><label>Customer</label><input value={f.customer} onChange={(e) => set("customer", e.target.value)} /></div>
      </div>
      <label>Description</label>
      <textarea value={f.description} onChange={(e) => set("description", e.target.value)} style={{ minHeight: 70, fontFamily: "inherit" }} />
      <div className="field-row">
        <div>
          <label>Status</label>
          <select value={f.status} onChange={(e) => set("status", e.target.value)}>
            {["active", "planned", "on_hold", "completed", "archived"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
          </select>
        </div>
        <div>
          <label>Health</label>
          <select value={f.health} onChange={(e) => set("health", e.target.value)}>
            {["green", "yellow", "red"].map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label>Progress %</label>
          <input type="number" min={0} max={100} value={f.progress} onChange={(e) => set("progress", e.target.value)} />
        </div>
      </div>
      <div className="field-row">
        <div><label>Start date</label><input type="date" value={f.start_date} onChange={(e) => set("start_date", e.target.value)} /></div>
        <div><label>End date</label><input type="date" value={f.end_date} onChange={(e) => set("end_date", e.target.value)} /></div>
      </div>
      <div className="field-row">
        <div><label>Manager</label><input value={f.manager} onChange={(e) => set("manager", e.target.value)} /></div>
        <div><label>Tech owner</label><input value={f.tech_owner} onChange={(e) => set("tech_owner", e.target.value)} /></div>
      </div>
      <div className="field-row">
        <div><label>Jira project key</label><input value={f.jira_project} onChange={(e) => set("jira_project", e.target.value)} /></div>
        <div><label>Splunk env</label><input value={f.splunk_env} onChange={(e) => set("splunk_env", e.target.value)} /></div>
      </div>
      <label>Notes</label>
      <textarea value={f.notes} onChange={(e) => set("notes", e.target.value)} style={{ minHeight: 70, fontFamily: "inherit" }} />
    </Modal>
  );
}
