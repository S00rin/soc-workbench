import { useEffect, useState } from "react";
import { api } from "../api";
import { useAccess } from "../access";
import { Loading, Modal, timeAgo, useToast } from "../lib";

type User = {
  id: number; username: string; display_name: string; email: string; role: "admin" | "analyst" | "viewer";
  module_permissions: string[]; active: boolean; must_change_password: boolean; last_login_at?: string;
};
type Feature = {
  key: string; label: string; module: string; enabled: boolean; active: boolean; status: string;
  starts_at?: string | null; expires_at?: string | null; allowed_roles?: string[]; config?: Record<string, unknown>;
};

export default function AccessAdmin() {
  const [tab, setTab] = useState<"users" | "features" | "activity">("users");
  return <>
    <div className="page-intro"><div><h1>Access & Feature Control</h1><p>Create users, limit module access and schedule when product features start or expire.</p></div></div>
    <div className="tabs hub-tabs">
      <button className={`tab ${tab === "users" ? "active" : ""}`} onClick={() => setTab("users")}>Users & roles</button>
      <button className={`tab ${tab === "features" ? "active" : ""}`} onClick={() => setTab("features")}>Feature availability</button>
      <button className={`tab ${tab === "activity" ? "active" : ""}`} onClick={() => setTab("activity")}>Activity history</button>
    </div>
    {tab === "users" && <UsersPanel />}
    {tab === "features" && <FeaturesPanel />}
    {tab === "activity" && <ActivityPanel />}
  </>;
}

function UsersPanel() {
  const access = useAccess();
  const toast = useToast();
  const [rows, setRows] = useState<User[] | null>(null);
  const [editing, setEditing] = useState<User | "new" | null>(null);
  async function load() { setRows(await api.get("/api/admin/users")); }
  useEffect(() => { load().catch(error => toast(error.message, "error")); }, []);
  async function deactivate(row: User) {
    if (!confirm(`Deactivate ${row.username}? Their existing session will stop working.`)) return;
    try { await api.del(`/api/admin/users/${row.id}`); await load(); toast("User deactivated", "ok"); }
    catch (error: any) { toast(error.message, "error"); }
  }
  async function reset(row: User) {
    const password = prompt(`New temporary password for ${row.username} (minimum 12 characters)`);
    if (!password) return;
    try { await api.post(`/api/admin/users/${row.id}/reset-password`, { password, must_change_password: true }); toast("Temporary password set", "ok"); }
    catch (error: any) { toast(error.message, "error"); }
  }
  if (!rows) return <Loading />;
  return <>
    <div className="row mb"><div className="notice compact">Permissions are enforced by the backend on every request. Admins always receive all modules.</div><span className="spacer" /><button className="btn-primary btn-sm" onClick={() => setEditing("new")}>+ New user</button></div>
    <div className="card table-card"><table className="data"><thead><tr><th>User</th><th>Role</th><th>Modules</th><th>Status</th><th>Last login</th><th></th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td><b>{row.display_name || row.username}</b><div className="faint mono">{row.username}{row.email ? ` · ${row.email}` : ""}</div></td><td><span className={`badge ${row.role === "admin" ? "purple" : row.role === "analyst" ? "blue" : ""}`}>{row.role}</span></td><td><div className="module-chips">{row.role === "admin" ? <span className="chip">All modules</span> : row.module_permissions.map(item => <span className="chip" key={item}>{item}</span>)}</div></td><td><span className={`badge ${row.active ? "green" : "red"}`}>{row.active ? "Active" : "Inactive"}</span>{row.must_change_password && <span className="badge yellow">Password change</span>}</td><td>{row.last_login_at ? timeAgo(row.last_login_at) : "Never"}</td><td><div className="row"><button className="btn-sm" onClick={() => setEditing(row)}>Edit</button><button className="btn-sm" onClick={() => reset(row)}>Reset password</button>{row.id !== access.user.id && row.active && <button className="btn-sm btn-danger" onClick={() => deactivate(row)}>Deactivate</button>}</div></td></tr>)}</tbody></table></div>
    {editing && <UserModal initial={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
  </>;
}

function UserModal({ initial, onClose, onSaved }: { initial: User | null; onClose: () => void; onSaved: () => void }) {
  const access = useAccess();
  const toast = useToast();
  const [form, setForm] = useState<any>(initial ? { ...initial } : {
    username: "", display_name: "", email: "", password: "", role: "analyst",
    module_permissions: ["dashboard", "data", "integrations"], active: true, must_change_password: true,
  });
  const [busy, setBusy] = useState(false);
  const set = (key: string, value: any) => setForm((previous: any) => ({ ...previous, [key]: value }));
  function toggleModule(key: string) {
    const values = new Set<string>(form.module_permissions || []);
    values.has(key) ? values.delete(key) : values.add(key);
    set("module_permissions", Array.from(values));
  }
  async function save() {
    setBusy(true);
    try {
      if (initial) {
        const { username: _username, password: _password, id: _id, ...payload } = form;
        await api.put(`/api/admin/users/${initial.id}`, payload);
      } else await api.post("/api/admin/users", form);
      toast("User access saved", "ok"); onSaved();
    } catch (error: any) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }
  return <Modal title={initial ? `Edit ${initial.username}` : "Create user"} onClose={onClose} wide footer={<><button onClick={onClose}>Cancel</button><button className="btn-primary" onClick={save} disabled={busy}>{busy ? <span className="spin" /> : "Save user"}</button></>}>
    {!initial && <><label>Username</label><input autoComplete="off" value={form.username} onChange={event => set("username", event.target.value)} /></>}
    <div className="field-row"><div><label>Display name</label><input value={form.display_name} onChange={event => set("display_name", event.target.value)} /></div><div><label>Email</label><input type="email" value={form.email} onChange={event => set("email", event.target.value)} /></div></div>
    {!initial && <><label>Temporary password</label><input type="password" autoComplete="new-password" value={form.password} onChange={event => set("password", event.target.value)} /><div className="faint">Minimum 12 characters. The user can be forced to change it after first login.</div></>}
    <label>Role</label><select value={form.role} onChange={event => set("role", event.target.value)}><option value="viewer">Viewer</option><option value="analyst">Analyst</option><option value="admin">Admin</option></select>
    <label>Allowed modules</label><div className={`module-selector ${form.role === "admin" ? "disabled" : ""}`}>{access.module_catalog.map(item => <label className="module-option" key={item.key}><input type="checkbox" disabled={form.role === "admin"} checked={form.role === "admin" || form.module_permissions.includes(item.key)} onChange={() => toggleModule(item.key)} /><span><b>{item.label}</b><small>{item.description}</small></span></label>)}</div>
    <div className="check-row mt"><label><input type="checkbox" checked={form.active} onChange={event => set("active", event.target.checked)} /> Active account</label><label><input type="checkbox" checked={form.must_change_password} onChange={event => set("must_change_password", event.target.checked)} /> Require password change</label></div>
  </Modal>;
}

function FeaturesPanel() {
  const toast = useToast();
  const [rows, setRows] = useState<Feature[] | null>(null);
  async function load() { setRows(await api.get("/api/admin/features")); }
  useEffect(() => { load().catch(error => toast(error.message, "error")); }, []);
  if (!rows) return <Loading />;
  return <div className="feature-grid">{rows.map(row => <FeatureCard key={row.key} row={row} onSaved={load} />)}</div>;
}

function localDate(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function FeatureCard({ row, onSaved }: { row: Feature; onSaved: () => void }) {
  const toast = useToast();
  const [enabled, setEnabled] = useState(row.enabled);
  const [startsAt, setStartsAt] = useState(localDate(row.starts_at));
  const [expiresAt, setExpiresAt] = useState(localDate(row.expires_at));
  const [roles, setRoles] = useState<string[]>(row.allowed_roles || []);
  const [busy, setBusy] = useState(false);
  function preset(days: number | null) {
    if (days === null) return setExpiresAt("");
    const date = new Date(Date.now() + days * 86400000);
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    setExpiresAt(local.toISOString().slice(0, 16));
  }
  function toggleRole(role: string) { setRoles(previous => previous.includes(role) ? previous.filter(item => item !== role) : [...previous, role]); }
  async function save() {
    setBusy(true);
    try {
      await api.put(`/api/admin/features/${encodeURIComponent(row.key)}`, {
        enabled, starts_at: startsAt ? new Date(startsAt).toISOString() : null,
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
        allowed_roles: roles, config: row.config || {},
      });
      toast(`${row.label} policy saved`, "ok"); await onSaved();
    } catch (error: any) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }
  return <div className="card feature-card">
    <div className="card-head"><div><h3>{row.label}</h3><span className="mono faint">{row.key}</span></div><span className={`badge ${row.status === "active" ? "green" : row.status === "scheduled" ? "yellow" : "red"}`}>{row.status}</span></div>
    <label className="switch-line"><input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)} /><span>Feature enabled</span></label>
    <div className="field-row"><div><label>Starts at</label><input type="datetime-local" value={startsAt} onChange={event => setStartsAt(event.target.value)} /></div><div><label>Expires at</label><input type="datetime-local" value={expiresAt} onChange={event => setExpiresAt(event.target.value)} /></div></div>
    <div className="row preset-row"><span className="faint">Duration:</span>{[7, 30, 90].map(days => <button className="btn-sm" key={days} onClick={() => preset(days)}>{days} days</button>)}<button className="btn-sm" onClick={() => preset(null)}>Unlimited</button></div>
    <label>Allowed roles <span className="faint">(none = all)</span></label><div className="check-row">{["viewer", "analyst", "admin"].map(role => <label key={role}><input type="checkbox" checked={roles.includes(role)} onChange={() => toggleRole(role)} /> {role}</label>)}</div>
    <div className="row mt"><span className="spacer" /><button className="btn-primary btn-sm" onClick={save} disabled={busy}>{busy ? <span className="spin" /> : "Save policy"}</button></div>
  </div>;
}

function ActivityPanel() {
  const toast = useToast();
  const [value, setValue] = useState<any>(null);
  const [actor, setActor] = useState("");
  const [module, setModule] = useState("");
  async function load() {
    const query = new URLSearchParams({ page_size: "100" });
    if (actor) query.set("actor", actor); if (module) query.set("module", module);
    setValue(await api.get(`/api/admin/activity?${query}`));
  }
  useEffect(() => { load().catch(error => toast(error.message, "error")); }, []);
  if (!value) return <Loading />;
  return <div className="card table-card"><div className="card-head"><h3>{value.total} recorded action(s)</h3><div className="row"><input style={{ width: 180 }} placeholder="User" value={actor} onChange={event => setActor(event.target.value)} /><input style={{ width: 180 }} placeholder="Module" value={module} onChange={event => setModule(event.target.value)} /><button className="btn-sm" onClick={load}>Filter</button></div></div><table className="data"><thead><tr><th>Time</th><th>User</th><th>Module</th><th>Action</th><th>Status</th><th>Trace</th></tr></thead><tbody>{value.items.map((row: any) => <tr key={row.id}><td>{timeAgo(row.created_at)}</td><td>{row.actor_user_id}</td><td><span className="badge">{row.module_key}</span></td><td className="mono">{row.action}</td><td><span className={`badge ${row.status_code < 400 ? "green" : "red"}`}>{row.status_code}</span></td><td className="mono faint">{row.correlation_id?.slice(0, 10)}</td></tr>)}</tbody></table></div>;
}
