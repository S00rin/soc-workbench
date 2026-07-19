import { useEffect, useState } from "react";
import { api } from "../api";
import { useAccess } from "../access";
import { Loading, Modal, useToast } from "../lib";

type Connection = {
  id: number; name: string; base_url: string; verify_ssl: boolean; timeout: number;
  enabled: boolean; ai_enabled: boolean; has_credentials: boolean; last_success_at?: string;
  last_error_code?: string; last_error_summary?: string;
};

const emptyForm = { name: "Wiki.js", base_url: "", api_token: "", verify_ssl: true, timeout: 30, enabled: true, ai_enabled: true };

export default function WikiJS() {
  const access = useAccess();
  const toast = useToast();
  const [rows, setRows] = useState<Connection[] | null>(null);
  const [editing, setEditing] = useState<Connection | "new" | null>(null);
  const [testing, setTesting] = useState<number | null>(null);
  const [capabilities, setCapabilities] = useState<Record<number, any>>({});
  const [selected, setSelected] = useState(0);
  const [search, setSearch] = useState("");
  const [pages, setPages] = useState<any[] | null>(null);

  async function load() {
    const value = await api.get("/api/wikijs/connections");
    setRows(value);
    setSelected(current => current || value[0]?.id || 0);
  }
  useEffect(() => { load().catch(error => toast(error.message, "error")); }, []);

  async function test(row: Connection) {
    setTesting(row.id);
    try {
      const value = await api.post(`/api/wikijs/connections/${row.id}/test`);
      setCapabilities(previous => ({ ...previous, [row.id]: value.capabilities }));
      await load();
      toast(value.capabilities.can_connect.allowed ? "Wiki.js connection is ready" : "Wiki.js needs attention", value.capabilities.can_connect.allowed ? "ok" : "error");
    } catch (error: any) { toast(error.message, "error"); }
    finally { setTesting(null); }
  }

  async function remove(row: Connection) {
    if (!confirm(`Delete Wiki.js connection “${row.name}”?`)) return;
    try { await api.del(`/api/wikijs/connections/${row.id}`); await load(); }
    catch (error: any) { toast(error.message, "error"); }
  }

  async function findPages() {
    if (!selected) return;
    try {
      const value = await api.post(`/api/wikijs/connections/${selected}/search`, { query: search, limit: 50 });
      setPages(value.items || []);
    } catch (error: any) { toast(error.message, "error"); }
  }

  if (!rows) return <Loading />;
  return <>
    <div className="row mb"><div><h2>Wiki.js connections</h2><p className="dim">Official GraphQL API connection with encrypted token storage and permission testing.</p></div><span className="spacer" />{access.user.role === "admin" && <button className="btn-primary btn-sm" onClick={() => setEditing("new")}>+ Add Wiki.js</button>}</div>
    {rows.length === 0 ? <div className="card empty">No Wiki.js connection yet. Create an API key in Wiki.js Administration → API Access, then add it here.</div> : <div className="grid cols-2 mb">
      {rows.map(row => <div className="card connection-card" key={row.id}>
        <div className="card-head"><div><h3>{row.name}</h3><span className={`badge ${row.last_error_code ? "red" : row.last_success_at ? "green" : "yellow"}`}>{row.last_error_code ? "Action required" : row.last_success_at ? "Connected" : "Not tested"}</span></div><span className="badge blue">Wiki.js</span></div>
        <div className="connection-url mono">{row.base_url}</div>
        <div className="connection-meta"><span>Token: {row.has_credentials ? "configured" : "missing"}</span><span>AI: {row.ai_enabled ? "enabled" : "disabled"}</span></div>
        {row.last_error_summary && <div className="action-error"><b>{row.last_error_code}</b>{row.last_error_summary}</div>}
        <div className="row mt"><button className="btn-sm" disabled={testing === row.id} onClick={() => test(row)}>{testing === row.id ? <span className="spin" /> : "Test & permissions"}</button>{access.user.role === "admin" && <><button className="btn-sm" onClick={() => setEditing(row)}>Edit</button><span className="spacer" /><button className="btn-sm btn-danger" onClick={() => remove(row)}>Delete</button></>}</div>
        {capabilities[row.id] && <div className="capability-grid">{Object.entries(capabilities[row.id]).map(([name, info]: any) => <div key={name} className={info.allowed ? "allowed" : "denied"}><span>{info.allowed ? "✓" : "×"}</span><div><b>{name.replace(/_/g, " ")}</b>{info.error?.action && <small>{info.error.action}</small>}</div></div>)}</div>}
      </div>)}
    </div>}
    {rows.length > 0 && <div className="card"><div className="card-head"><h3>Page search</h3><select style={{ maxWidth: 260 }} value={selected} onChange={event => setSelected(Number(event.target.value))}>{rows.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></div><div className="row"><input value={search} onChange={event => setSearch(event.target.value)} onKeyDown={event => event.key === "Enter" && findPages()} placeholder="Search title or path…" /><button className="btn-primary" onClick={findPages}>Search</button></div>{pages && <div className="list mt">{pages.length === 0 ? <div className="empty">No matching pages.</div> : pages.map(page => <div className="list-row" key={page.id}><div><b>{page.title}</b><div className="mono faint">/{page.path}</div></div><span className="badge">#{page.id}</span></div>)}</div>}</div>}
    {editing && <WikiConnectionModal initial={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
  </>;
}

function WikiConnectionModal({ initial, onClose, onSaved }: { initial: Connection | null; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [form, setForm] = useState<any>(initial ? { ...emptyForm, ...initial, api_token: "" } : emptyForm);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      if (initial) await api.put(`/api/wikijs/connections/${initial.id}`, form);
      else await api.post("/api/wikijs/connections", form);
      toast("Wiki.js connection saved", "ok"); onSaved();
    } catch (error: any) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }
  const set = (key: string, value: any) => setForm((previous: any) => ({ ...previous, [key]: value }));
  return <Modal title={initial ? "Edit Wiki.js connection" : "Add Wiki.js connection"} onClose={onClose} footer={<><button onClick={onClose}>Cancel</button><button className="btn-primary" onClick={save} disabled={busy}>{busy ? <span className="spin" /> : "Save"}</button></>}>
    <label>Name</label><input value={form.name} onChange={event => set("name", event.target.value)} />
    <label>Base URL</label><input className="mono" placeholder="https://wiki.company.local" value={form.base_url} onChange={event => set("base_url", event.target.value)} />
    <label>API token {initial?.has_credentials && <span className="faint">(leave blank to keep existing)</span>}</label><input type="password" autoComplete="new-password" value={form.api_token} onChange={event => set("api_token", event.target.value)} />
    <div className="field-row"><div><label>Timeout</label><input type="number" min={5} max={120} value={form.timeout} onChange={event => set("timeout", Number(event.target.value))} /></div><div><label>Policies</label><div className="check-row wrap"><label><input type="checkbox" checked={form.verify_ssl} onChange={event => set("verify_ssl", event.target.checked)} /> Verify TLS</label><label><input type="checkbox" checked={form.enabled} onChange={event => set("enabled", event.target.checked)} /> Enabled</label><label><input type="checkbox" checked={form.ai_enabled} onChange={event => set("ai_enabled", event.target.checked)} /> AI enabled</label></div></div></div>
  </Modal>;
}
