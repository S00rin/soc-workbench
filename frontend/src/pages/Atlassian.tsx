import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Loading, Modal, useToast } from "../lib";
import "./Atlassian.css";

type Product = "jira" | "confluence";
type Connection = {
  id: number; name: string; products: Product[]; deployment_type: "cloud" | "data_center";
  auth_type: "api_token" | "pat" | "basic" | "oauth2"; base_url: string; cloud_id: string;
  username: string; scopes: string[]; verify_ssl: boolean; timeout: number; enabled: boolean;
  ai_enabled: boolean; auto_post_enabled: boolean; bulk_auto_post_enabled: boolean;
  has_credentials: boolean; last_test_at?: string; last_success_at?: string;
  last_error_code?: string; last_error_summary?: string;
};

const TABS = ["connections", "jira", "confluence", "mapping", "history", "bulk"] as const;
type Tab = typeof TABS[number];

const tabLabels: Record<Tab, string> = {
  connections: "Connections", jira: "Jira", confluence: "Confluence",
  mapping: "Field Mapping", history: "Query & Prompt History", bulk: "Bulk Operations",
};

export default function Atlassian() {
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [tab, setTab] = useState<Tab>("connections");
  const [selectedId, setSelectedId] = useState<number>(0);
  const toast = useToast();

  async function loadConnections() {
    try {
      const rows = await api.get("/api/atlassian/connections");
      setConnections(rows);
      setSelectedId((current) => current || rows[0]?.id || 0);
    } catch (error: any) { toast(error.message, "error"); }
  }

  useEffect(() => { loadConnections(); }, []);
  if (!connections) return <Loading />;
  const selected = connections.find((item) => item.id === selectedId) || connections[0];

  return <div className="atlassian-page">
    <div className="atlassian-head mb">
      <div><h1>Atlassian Integrations</h1><p>Secure Jira and Confluence connections, mapping, audit history, and controlled AI comments.</p></div>
      {connections.length > 0 && <select value={selected?.id || ""} onChange={(event) => setSelectedId(Number(event.target.value))} aria-label="Active Atlassian connection">
        {connections.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>}
    </div>
    <div className="tabs">
      {TABS.map((item) => <button key={item} className={`tab ${tab === item ? "active" : ""}`} onClick={() => setTab(item)}>{tabLabels[item]}</button>)}
    </div>
    {tab === "connections" && <ConnectionsPanel rows={connections} onChanged={loadConnections} />}
    {tab !== "connections" && !selected && <div className="card empty">Create an Atlassian connection first.</div>}
    {tab === "jira" && selected && <JiraWorkspace connection={selected} />}
    {tab === "confluence" && selected && <ConfluenceWorkspace connection={selected} />}
    {tab === "mapping" && selected && <MappingPanel connection={selected} />}
    {tab === "history" && <HistoryPanel connections={connections} />}
    {tab === "bulk" && selected && <BulkPanel connection={selected} />}
  </div>;
}

function ConnectionsPanel({ rows, onChanged }: { rows: Connection[]; onChanged: () => void }) {
  const [editing, setEditing] = useState<Connection | null | "new">(null);
  const [testing, setTesting] = useState<number | null>(null);
  const [capabilities, setCapabilities] = useState<Record<number, any>>({});
  const toast = useToast();

  async function test(row: Connection) {
    setTesting(row.id);
    try {
      const result = await api.post(`/api/atlassian/connections/${row.id}/test`);
      setCapabilities((previous) => ({ ...previous, [row.id]: result.capabilities }));
      toast("Connection and capability checks completed", "ok");
      onChanged();
    } catch (error: any) { toast(error.message, "error"); }
    finally { setTesting(null); }
  }

  async function remove(row: Connection) {
    if (!confirm(`Delete connection “${row.name}”? Existing history remains but mappings and bulk jobs for it are removed.`)) return;
    try { await api.del(`/api/atlassian/connections/${row.id}`); toast("Connection deleted", "ok"); onChanged(); }
    catch (error: any) { toast(error.message, "error"); }
  }

  async function authorize(row: Connection) {
    try {
      const result = await api.get(`/api/atlassian/connections/${row.id}/oauth/start`);
      location.href = result.authorization_url;
    } catch (error: any) { toast(error.message, "error"); }
  }

  return <>
    <div className="row mb"><span className="spacer" /><button className="btn-primary btn-sm" onClick={() => setEditing("new")}>+ Add connection</button></div>
    {rows.length === 0 ? <div className="card empty">No connection yet. Add Jira, Confluence, or a shared Atlassian connection.</div> :
      <div className="grid cols-2">
        {rows.map((row) => <div className="card connection-card" key={row.id}>
          <div className="card-head"><div><h3>{row.name}</h3><div className="row">{row.products.map((product) => <span key={product} className="badge blue">{product}</span>)}<span className="badge">{row.deployment_type}</span><span className="badge">{row.auth_type}</span></div></div><ConnectionStatus row={row} /></div>
          <div className="connection-url mono">{row.base_url}</div>
          <div className="connection-meta"><span>Credentials: {row.has_credentials ? "configured" : "missing"}</span><span>Last success: {fmt(row.last_success_at)}</span></div>
          {row.last_error_summary && <div className="action-error"><b>{row.last_error_code}</b>{row.last_error_summary}</div>}
          <div className="row mt">
            <button className="btn-sm" onClick={() => test(row)} disabled={testing === row.id}>{testing === row.id ? <span className="spin" /> : "Test & permissions"}</button>
            {row.auth_type === "oauth2" && <button className="btn-sm" onClick={() => authorize(row)}>Reconnect OAuth</button>}
            <button className="btn-sm" onClick={() => setEditing(row)}>Edit</button>
            <span className="spacer" /><button className="btn-sm btn-danger" onClick={() => remove(row)}>Delete</button>
          </div>
          {capabilities[row.id] && <CapabilityMatrix value={capabilities[row.id]} />}
        </div>)}
      </div>}
    {editing && <ConnectionModal initial={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); onChanged(); }} />}
  </>;
}

function ConnectionStatus({ row }: { row: Connection }) {
  if (row.last_error_code) return <span className="badge red">Action required</span>;
  if (row.last_success_at) return <span className="badge green">Connected</span>;
  return <span className="badge yellow">Not tested</span>;
}

function CapabilityMatrix({ value }: { value: any }) {
  return <div className="capability-grid">
    {Object.entries(value).flatMap(([product, capabilities]: any) => Object.entries(capabilities || {}).map(([name, info]: any) =>
      <div key={`${product}-${name}`} className={info.allowed === true ? "allowed" : info.allowed === false ? "denied" : "unknown"}>
        <span>{info.allowed === true ? "✓" : info.allowed === false ? "×" : "?"}</span><div><b>{human(name)}</b><small>{product}{info.error?.action ? ` · ${info.error.action}` : ""}</small></div>
      </div>))}
  </div>;
}

function ConnectionModal({ initial, onClose, onSaved }: { initial: Connection | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<any>(initial ? { ...initial, credentials: {} } : {
    name: "", products: ["jira"], deployment_type: "cloud", auth_type: "api_token", base_url: "",
    cloud_id: "", username: "", credentials: {}, scopes: [], verify_ssl: true, timeout: 30,
    enabled: true, ai_enabled: true, auto_post_enabled: false, bulk_auto_post_enabled: false,
  });
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const set = (key: string, value: any) => setForm((previous: any) => ({ ...previous, [key]: value }));
  const setSecret = (key: string, value: string) => setForm((previous: any) => ({ ...previous, credentials: { ...previous.credentials, [key]: value } }));
  const credentialKey = form.auth_type === "api_token" ? "api_token" : form.auth_type === "pat" ? "pat" : form.auth_type === "basic" ? "password" : "";

  async function save() {
    if (!form.name.trim() || !form.base_url.trim()) return toast("Name and base URL are required", "error");
    setBusy(true);
    try {
      if (initial) await api.put(`/api/atlassian/connections/${initial.id}`, form);
      else await api.post("/api/atlassian/connections", form);
      toast("Connection saved", "ok"); onSaved();
    } catch (error: any) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }

  function toggleProduct(product: Product) {
    const products = form.products.includes(product) ? form.products.filter((item: Product) => item !== product) : [...form.products, product];
    if (products.length) set("products", products);
  }

  return <Modal title={initial ? "Edit Atlassian connection" : "Add Atlassian connection"} onClose={onClose} wide footer={<><button className="btn-sm" onClick={onClose}>Cancel</button><button className="btn-primary btn-sm" onClick={save} disabled={busy}>{busy ? <span className="spin" /> : "Save connection"}</button></>}>
    <div className="field-row"><div><label>Name</label><input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Production Atlassian" /></div><div><label>Products</label><div className="check-row"><label><input type="checkbox" checked={form.products.includes("jira")} onChange={() => toggleProduct("jira")} /> Jira</label><label><input type="checkbox" checked={form.products.includes("confluence")} onChange={() => toggleProduct("confluence")} /> Confluence</label></div></div></div>
    <div className="field-row"><div><label htmlFor="atlassian-deployment">Deployment</label><select id="atlassian-deployment" value={form.deployment_type} onChange={(e) => set("deployment_type", e.target.value)}><option value="cloud">Cloud</option><option value="data_center">Data Center</option></select></div><div><label htmlFor="atlassian-authentication">Authentication</label><select id="atlassian-authentication" value={form.auth_type} onChange={(e) => set("auth_type", e.target.value)}><option value="api_token">Cloud API token</option><option value="pat">Data Center PAT</option><option value="basic">Username & password</option><option value="oauth2">OAuth 2.0 (3LO)</option></select></div></div>
    <label>Base URL</label><input value={form.base_url} onChange={(e) => set("base_url", e.target.value)} className="mono" placeholder="https://company.atlassian.net" />
    <div className="field-row"><div><label>Email / username</label><input value={form.username} onChange={(e) => set("username", e.target.value)} /></div>{credentialKey && <div><label>{human(credentialKey)} {initial?.has_credentials && <span className="faint">(leave blank to keep)</span>}</label><input type="password" value={form.credentials[credentialKey] || ""} onChange={(e) => setSecret(credentialKey, e.target.value)} /></div>}</div>
    {form.auth_type === "oauth2" && <div className="notice">Save first, then use “Reconnect OAuth”. OAuth Client ID/Secret and redirect URI are configured through environment variables.</div>}
    <div className="field-row"><div><label>Timeout (seconds)</label><input type="number" min={5} max={180} value={form.timeout} onChange={(e) => set("timeout", Number(e.target.value))} /></div><div><label>Security policies</label><div className="check-row wrap"><label><input type="checkbox" checked={form.verify_ssl} onChange={(e) => set("verify_ssl", e.target.checked)} /> Verify TLS</label><label><input type="checkbox" checked={form.ai_enabled} onChange={(e) => set("ai_enabled", e.target.checked)} /> AI enabled</label><label><input type="checkbox" checked={form.auto_post_enabled} onChange={(e) => set("auto_post_enabled", e.target.checked)} /> Auto-post</label><label><input type="checkbox" checked={form.bulk_auto_post_enabled} onChange={(e) => set("bulk_auto_post_enabled", e.target.checked)} /> Bulk auto-post</label></div></div></div>
  </Modal>;
}

function JiraWorkspace({ connection }: { connection: Connection }) {
  const [jql, setJql] = useState("assignee = currentUser() ORDER BY updated DESC");
  const [issues, setIssues] = useState<any[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [commentIssue, setCommentIssue] = useState<string | null>(null);
  const toast = useToast();
  async function search() {
    setBusy(true);
    try { const result = await api.post(`/api/atlassian/connections/${connection.id}/jira/search`, { jql, max_results: 50 }); setIssues(result.issues); }
    catch (error: any) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }
  if (!connection.products.includes("jira")) return <div className="card empty">Jira is not enabled on this connection.</div>;
  return <>
    <div className="card mb"><div className="card-head"><h3>JQL Search</h3><span className="badge blue">{connection.name}</span></div><textarea value={jql} onChange={(e) => setJql(e.target.value)} style={{ minHeight: 70 }} /><div className="row mt"><button className="btn-primary btn-sm" onClick={search} disabled={busy}>{busy ? <span className="spin" /> : "Search"}</button><span className="faint">Every query and result status is recorded with a correlation ID.</span></div></div>
    {issues && <div className="card"><div className="card-head"><h3>{issues.length} issue(s)</h3></div>{issues.length === 0 ? <div className="empty">No issues matched.</div> : <table className="data"><thead><tr><th>Key</th><th>Summary</th><th>Status</th><th>Priority</th><th></th></tr></thead><tbody>{issues.map((issue) => <tr key={issue.key}><td className="mono">{issue.key}</td><td>{issue.fields?.summary}</td><td><span className="badge">{issue.fields?.status?.name}</span></td><td>{issue.fields?.priority?.name || "—"}</td><td><button className="btn-sm" onClick={() => setCommentIssue(issue.key)}>Smart comment</button></td></tr>)}</tbody></table>}</div>}
    {commentIssue && <CommentComposer product="jira" connection={connection} targetId={commentIssue} onClose={() => setCommentIssue(null)} />}
  </>;
}

function ConfluenceWorkspace({ connection }: { connection: Connection }) {
  const [cql, setCql] = useState("type = page ORDER BY lastmodified DESC");
  const [results, setResults] = useState<any[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [commentPage, setCommentPage] = useState<string | null>(null);
  const [links, setLinks] = useState<Record<string, any[]>>({});
  const toast = useToast();
  async function search() {
    setBusy(true);
    try { const value = await api.post(`/api/atlassian/connections/${connection.id}/confluence/search`, { cql, limit: 50 }); setResults(value.results); const existing = await api.get(`/api/atlassian/connections/${connection.id}/content-links`); setLinks(existing.reduce((grouped: Record<string, any[]>, link: any) => { (grouped[link.confluence_page_id] ??= []).push(link); return grouped; }, {})); }
    catch (error: any) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }
  async function linkToJira(pageId: string) {
    const issueKey = prompt("Jira issue key to link (for example SOC-123)");
    if (!issueKey) return;
    try {
      await api.post(`/api/atlassian/connections/${connection.id}/content-links`, { jira_issue_key: issueKey, confluence_page_id: pageId, relation_type: "related" });
      const value = await api.get(`/api/atlassian/connections/${connection.id}/content-links?confluence_page_id=${encodeURIComponent(pageId)}`);
      setLinks((previous) => ({ ...previous, [pageId]: value }));
      toast("Jira issue and Confluence page linked", "ok");
    } catch (error: any) { toast(error.message, "error"); }
  }
  if (!connection.products.includes("confluence")) return <div className="card empty">Confluence is not enabled on this connection.</div>;
  return <><div className="card mb"><div className="card-head"><h3>CQL Search</h3><span className="badge blue">{connection.name}</span></div><textarea value={cql} onChange={(e) => setCql(e.target.value)} style={{ minHeight: 70 }} /><div className="row mt"><button className="btn-primary btn-sm" onClick={search} disabled={busy}>{busy ? <span className="spin" /> : "Search pages"}</button></div></div>
    {results && <div className="card"><div className="card-head"><h3>{results.length} page(s)</h3></div>{results.length === 0 ? <div className="empty">No pages matched.</div> : <table className="data"><thead><tr><th>ID</th><th>Title</th><th>Type / linked Jira</th><th></th></tr></thead><tbody>{results.map((item) => { const page = item.content || item; const pageId = String(page.id); return <tr key={page.id}><td className="mono">{page.id}</td><td>{page.title}</td><td>{page.type || "page"} {links[pageId]?.map((link) => <span className="badge blue" key={link.id}>{link.jira_issue_key}</span>)}</td><td><div className="row"><button className="btn-sm" onClick={() => linkToJira(pageId)}>Link Jira</button><button className="btn-sm" onClick={() => setCommentPage(pageId)}>Smart comment</button></div></td></tr>; })}</tbody></table>}</div>}
    {commentPage && <CommentComposer product="confluence" connection={connection} targetId={commentPage} onClose={() => setCommentPage(null)} />}
  </>;
}

function CommentComposer({ product, connection, targetId, onClose }: { product: Product; connection: Connection; targetId: string; onClose: () => void }) {
  const [instruction, setInstruction] = useState("Review the current context and propose the next factual action.");
  const [language, setLanguage] = useState("fa");
  const [tone, setTone] = useState("formal");
  const [preview, setPreview] = useState<any>(null);
  const [text, setText] = useState("");
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const base = product === "jira" ? `jira/issues/${targetId}` : `confluence/pages/${targetId}`;
  async function generate() {
    setBusy(true); setApproved(false);
    try { const value = await api.post(`/api/atlassian/connections/${connection.id}/${base}/comments/preview`, { instruction, language, tone }); setPreview(value); setText(value.comment); }
    catch (error: any) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }
  async function post() {
    if (!approved) return toast("Approve the edited preview before posting", "error");
    setBusy(true);
    try { await api.post(`/api/atlassian/connections/${connection.id}/${base}/comments`, { text, approved: true, mode: "require_approval", idempotency_key: crypto.randomUUID(), language, tone }); toast("Comment posted", "ok"); onClose(); }
    catch (error: any) { toast(error.message, "error"); }
    finally { setBusy(false); }
  }
  return <Modal title={`${product === "jira" ? "Jira issue" : "Confluence page"} ${targetId} · Smart comment`} onClose={onClose} wide footer={<><button className="btn-sm" onClick={onClose}>Cancel</button>{preview && <button className="btn-primary btn-sm" onClick={post} disabled={busy || !approved}>Post approved comment</button>}</>}>
    <div className="notice danger">Issue/page content is treated as untrusted context. The model cannot authorize posting; you must review and approve the final text.</div>
    <label>Instruction</label><textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} style={{ minHeight: 70, fontFamily: "inherit" }} />
    <div className="field-row"><div><label>Language</label><select value={language} onChange={(e) => setLanguage(e.target.value)}><option value="fa">Persian</option><option value="en">English</option></select></div><div><label>Tone</label><select value={tone} onChange={(e) => setTone(e.target.value)}>{["formal", "technical", "concise", "executive", "follow_up", "incident_response"].map((item) => <option key={item}>{item}</option>)}</select></div></div>
    <div className="row mt"><button className="btn-primary btn-sm" onClick={generate} disabled={busy}>{busy ? <span className="spin" /> : preview ? "Regenerate" : "Generate preview"}</button></div>
    {preview && <><label>Editable preview</label><textarea value={text} onChange={(e) => { setText(e.target.value); setApproved(false); }} style={{ minHeight: 150, fontFamily: "inherit" }} />
      <div className="row"><span className={`badge ${preview.duplicate_warning ? "red" : "green"}`}>{preview.duplicate_warning ? "Similar comment detected" : "No close duplicate detected"}</span><span className="badge">{preview.provider} · {preview.model}</span></div>
      <label className="approval"><input type="checkbox" checked={approved} onChange={(e) => setApproved(e.target.checked)} /> I reviewed this exact text and approve posting it.</label></>}
  </Modal>;
}

function MappingPanel({ connection }: { connection: Connection }) {
  const [product, setProduct] = useState<Product>(connection.products.includes("jira") ? "jira" : "confluence");
  const [internal, setInternal] = useState<any[]>([]);
  const [external, setExternal] = useState<any[]>([]);
  const [mappings, setMappings] = useState<any[]>([]);
  const [projects, setProjects] = useState<any[]>([]);
  const [projectKey, setProjectKey] = useState("");
  const [issueTypes, setIssueTypes] = useState<any[]>([]);
  const [issueTypeId, setIssueTypeId] = useState("");
  const [scope, setScope] = useState("connection");
  const [internalId, setInternalId] = useState("");
  const [externalId, setExternalId] = useState("");
  const [transform, setTransform] = useState("identity");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [importText, setImportText] = useState("");
  const [sample, setSample] = useState('{"title":"Sample incident","severity":"high","labels":["soc"]}');
  const [preview, setPreview] = useState<any>(null);
  const toast = useToast();
  async function load() {
    try {
      const [i, allMappings, p] = await Promise.all([api.get("/api/atlassian/internal-fields"), api.get(`/api/atlassian/connections/${connection.id}/mappings`), product === "jira" ? api.get(`/api/atlassian/connections/${connection.id}/jira/projects`) : Promise.resolve([])]);
      setInternal(i); setMappings(allMappings.filter((item: any) => item.product === product)); setProjects(p); setInternalId((v) => v || i[0]?.id || "");
    } catch (error: any) { toast(error.message, "error"); }
  }
  useEffect(() => { setExternal([]); setEditingId(null); load(); }, [connection.id, product]);
  useEffect(() => {
    if (product !== "jira" || !projectKey) { setIssueTypes([]); return; }
    api.get(`/api/atlassian/connections/${connection.id}/jira/issue-types?project_key=${encodeURIComponent(projectKey)}`).then(setIssueTypes).catch((e) => toast(e.message, "error"));
  }, [projectKey, product]);
  async function loadFields() {
    try { const result = await api.get(product === "jira" ? `/api/atlassian/connections/${connection.id}/jira/fields?project_key=${encodeURIComponent(projectKey)}&issue_type_id=${encodeURIComponent(issueTypeId)}` : `/api/atlassian/connections/${connection.id}/confluence/metadata-fields`); setExternal(result.fields); setExternalId(result.fields[0]?.id || ""); await load(); }
    catch (error: any) { toast(error.message, "error"); }
  }
  async function add() {
    const a = internal.find((item) => item.id === internalId); const b = external.find((item) => item.id === externalId);
    if (!a || !b) return toast("Select internal and Jira fields", "error");
    const body = { product, scope_type: product === "confluence" ? "connection" : scope, project_key: product === "jira" && scope !== "connection" ? projectKey : "", issue_type_id: product === "jira" && scope === "issue_type" ? issueTypeId : "", internal_field: a.id, internal_type: a.type, external_field_id: b.id, external_field_name: b.name, external_type: b.type, external_schema: b.schema, transformation: { op: transform }, required: b.required, read_only: b.read_only };
    try { if (editingId) await api.put(`/api/atlassian/mappings/${editingId}`, body); else await api.post(`/api/atlassian/connections/${connection.id}/mappings`, body); toast(editingId ? "Mapping updated" : "Mapping saved", "ok"); setEditingId(null); load(); }
    catch (error: any) { toast(error.message, "error"); }
  }
  function edit(item: any) {
    setEditingId(item.id); setScope(item.scope_type); setProjectKey(item.project_key || ""); setIssueTypeId(item.issue_type_id || "");
    setInternalId(item.internal_field); setExternalId(item.external_field_id); setTransform(item.transformation?.op || "identity");
    setExternal((previous) => previous.some((field) => field.id === item.external_field_id) ? previous : [...previous, { id: item.external_field_id, name: item.external_field_name, type: item.external_type, schema: item.external_schema, required: item.required, read_only: item.read_only }]);
  }
  async function remove(id: number) { if (!confirm("Delete this mapping?")) return; try { await api.del(`/api/atlassian/mappings/${id}`); load(); } catch (error: any) { toast(error.message, "error"); } }
  async function testPreview() { try { setPreview(await api.post(`/api/atlassian/connections/${connection.id}/mappings/preview`, { project_key: projectKey, issue_type_id: issueTypeId, source: JSON.parse(sample) })); } catch (error: any) { toast(error.message, "error"); } }
  async function exportMappings() { try { const value = await api.get(`/api/atlassian/connections/${connection.id}/mappings/export`); const blob = new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = `atlassian-mappings-${connection.id}.json`; a.click(); URL.revokeObjectURL(url); } catch (error: any) { toast(error.message, "error"); } }
  async function importMappings() { try { const value = JSON.parse(importText); const result = await api.post(`/api/atlassian/connections/${connection.id}/mappings/import`, value); toast(`Imported ${result.created}; ${result.errors.length} rejected`, result.errors.length ? "error" : "ok"); setImportText(""); load(); } catch (error: any) { toast(error.message, "error"); } }
  return <><div className="card mb"><div className="card-head"><h3>{product === "jira" ? "Dynamic Jira field metadata" : "Confluence metadata mapping"}</h3><button className="btn-sm" onClick={loadFields}>Refresh fields & validate mappings</button></div><div className="field-row"><div><label>Product</label><select value={product} onChange={(e) => setProduct(e.target.value as Product)}>{connection.products.map((item) => <option key={item} value={item}>{human(item)}</option>)}</select></div>{product === "jira" && <><div><label>Scope</label><select value={scope} onChange={(e) => setScope(e.target.value)}><option value="connection">Connection</option><option value="project">Project</option><option value="issue_type">Issue type</option></select></div><div><label>Project</label><select value={projectKey} onChange={(e) => setProjectKey(e.target.value)}><option value="">Select…</option>{projects.map((item) => <option key={item.id || item.key} value={item.key}>{item.key} · {item.name}</option>)}</select></div>{scope === "issue_type" && <div><label>Issue type</label><select value={issueTypeId} onChange={(e) => setIssueTypeId(e.target.value)}><option value="">Select…</option>{issueTypes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div>}</>}</div></div>
    <div className="card mb"><div className="card-head"><h3>{editingId ? "Edit field mapping" : "Add field mapping"}</h3><div className="row"><button className="btn-sm" onClick={() => setImportText('{\n  "version": 1,\n  "mappings": []\n}')}>Import JSON</button><button className="btn-sm" onClick={exportMappings}>Export JSON</button></div></div>{external.length === 0 ? <div className="empty">Select a product and click “Refresh fields”. Jira standard/custom fields and Confluence metadata capabilities are loaded from their providers.</div> : <><div className="mapping-builder"><div><label>Internal field</label><select value={internalId} onChange={(e) => setInternalId(e.target.value)}>{internal.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.type}</option>)}</select></div><span>→</span><div><label>{product === "jira" ? "Jira field" : "Confluence metadata"}</label><select value={externalId} onChange={(e) => setExternalId(e.target.value)}>{external.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.type}{item.required ? " · required" : ""}{item.read_only ? " · read-only" : ""}</option>)}</select></div><div><label>Transformation</label><select value={transform} onChange={(e) => setTransform(e.target.value)}>{["identity", "stringify", "number", "date_format", "join", "split", "map_values", "option", "user", "components", "adf"].map((item) => <option key={item}>{item}</option>)}</select></div><button className="btn-primary btn-sm" onClick={add}>{editingId ? "Update mapping" : "Save mapping"}</button>{editingId && <button className="btn-sm" onClick={() => setEditingId(null)}>Cancel</button>}</div></>}</div>
    <div className="card mb"><div className="card-head"><h3>Saved mappings</h3><span className="badge">{mappings.length}</span></div>{mappings.length === 0 ? <div className="empty">No mappings.</div> : <table className="data"><thead><tr><th>Scope</th><th>Internal</th><th>{human(product)}</th><th>Transform</th><th>Status</th><th></th></tr></thead><tbody>{mappings.map((item) => <tr key={item.id}><td>{item.scope_type}{item.project_key ? ` · ${item.project_key}` : ""}</td><td>{item.internal_field} <span className="faint">{item.internal_type}</span></td><td>{item.external_field_name || item.external_field_id} <span className="faint">{item.external_type}</span></td><td className="mono">{item.transformation?.op}</td><td><span className={`badge ${item.status === "valid" ? "green" : "red"}`}>{item.status}</span>{item.validation_message && <small className="mapping-warning">{item.validation_message}</small>}</td><td><div className="row"><button className="btn-sm" onClick={() => edit(item)}>Edit</button><button className="btn-sm btn-danger" onClick={() => remove(item.id)}>Delete</button></div></td></tr>)}</tbody></table>}</div>
    <div className="card"><div className="card-head"><h3>Test mapping preview</h3><button className="btn-primary btn-sm" onClick={testPreview}>Preview</button></div><textarea value={sample} onChange={(e) => setSample(e.target.value)} />{preview && <pre className="code-preview">{JSON.stringify(preview, null, 2)}</pre>}</div>
    {importText && <Modal title="Import Jira mappings" onClose={() => setImportText("")} wide footer={<><button className="btn-sm" onClick={() => setImportText("")}>Cancel</button><button className="btn-primary btn-sm" onClick={importMappings}>Validate & import</button></>}><div className="notice">Import validates every mapping independently. Existing mappings are preserved and rejected rows are reported.</div><textarea className="mono" value={importText} onChange={(e) => setImportText(e.target.value)} style={{ minHeight: 320 }} /></Modal>}
  </>;
}

function HistoryPanel({ connections }: { connections: Connection[] }) {
  const [rows, setRows] = useState<any[]>([]); const [total, setTotal] = useState(0); const [selected, setSelected] = useState<any>(null);
  const [filters, setFilters] = useState({ connection_id: "", owner_user_id: "", product: "", operation_type: "", status: "", project_key: "", issue: "", started_after: "", started_before: "", search: "" }); const [clone, setClone] = useState("");
  const toast = useToast();
  async function load() { const q = new URLSearchParams(Object.entries(filters).filter(([, value]) => value)); try { const value = await api.get(`/api/atlassian/history?${q}`); setRows(value.items); setTotal(value.total); } catch (error: any) { toast(error.message, "error"); } }
  useEffect(() => { load(); }, []);
  async function rerun(row: any, query = row.final_query) { try { const connection = connections.find((item) => item.id === row.connection_id); if (!connection) throw new Error("Connection no longer exists"); const endpoint = row.product === "jira" ? "jira/search" : "confluence/search"; const body = row.product === "jira" ? { jql: query, max_results: 50 } : { cql: query, limit: 50 }; const result = await api.post(`/api/atlassian/connections/${connection.id}/${endpoint}`, body); toast(`Re-run completed: ${result.total ?? result.results?.length ?? 0} result(s)`, "ok"); load(); } catch (error: any) { toast(error.message, "error"); } }
  async function remove(id: number) { if (!confirm("Delete this history item according to policy?")) return; try { await api.del(`/api/atlassian/history/${id}`); setSelected(null); load(); } catch (error: any) { toast(error.message, "error"); } }
  return <><div className="card mb"><div className="history-filters"><select value={filters.connection_id} onChange={(e) => setFilters({ ...filters, connection_id: e.target.value })}><option value="">All connections</option>{connections.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><select value={filters.product} onChange={(e) => setFilters({ ...filters, product: e.target.value })}><option value="">All products</option><option value="jira">Jira</option><option value="confluence">Confluence</option></select><select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}><option value="">All statuses</option><option value="success">Success</option><option value="partial">Partial</option><option value="failed">Failed</option></select><input value={filters.operation_type} onChange={(e) => setFilters({ ...filters, operation_type: e.target.value })} placeholder="Operation type" /><input value={filters.owner_user_id} onChange={(e) => setFilters({ ...filters, owner_user_id: e.target.value })} placeholder="User (admin)" /><input value={filters.project_key} onChange={(e) => setFilters({ ...filters, project_key: e.target.value })} placeholder="Project" /><input value={filters.issue} onChange={(e) => setFilters({ ...filters, issue: e.target.value })} placeholder="Issue / page" /><input type="datetime-local" value={filters.started_after} onChange={(e) => setFilters({ ...filters, started_after: e.target.value })} aria-label="Started after" /><input type="datetime-local" value={filters.started_before} onChange={(e) => setFilters({ ...filters, started_before: e.target.value })} aria-label="Started before" /><input value={filters.search} onChange={(e) => setFilters({ ...filters, search: e.target.value })} placeholder="Search redacted query or result…" /><button className="btn-primary btn-sm" onClick={load}>Filter</button></div><div className="row mt"><span className="faint">{total} record(s)</span><span className="spacer" /><button className="btn-sm" onClick={() => api.download("/api/atlassian/history-exports/json", "atlassian-history.json")}>Export JSON</button><button className="btn-sm" onClick={() => api.download("/api/atlassian/history-exports/csv", "atlassian-history.csv")}>Export CSV</button></div></div>
    <div className="card">{rows.length === 0 ? <div className="empty">No history matched.</div> : <table className="data"><thead><tr><th>Time</th><th>Product</th><th>Operation</th><th>Query/Targets</th><th>Status</th><th>Duration</th><th></th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{fmt(row.created_at)}</td><td>{row.product}</td><td>{row.operation_type}</td><td className="mono">{row.final_query?.slice(0, 70) || row.target_keys?.join(", ")}</td><td><span className={`badge ${row.status === "success" ? "green" : row.status === "failed" ? "red" : "yellow"}`}>{row.status}</span></td><td>{row.duration_ms} ms</td><td><button className="btn-sm" onClick={() => { setSelected(row); setClone(row.final_query || ""); }}>Details</button></td></tr>)}</tbody></table>}</div>
    {selected && <Modal title={`History #${selected.id}`} onClose={() => setSelected(null)} wide footer={<><button className="btn-danger btn-sm" onClick={() => remove(selected.id)}>Delete</button><span className="spacer" /><button className="btn-sm" onClick={() => rerun(selected)}>Re-run original</button><button className="btn-primary btn-sm" onClick={() => rerun(selected, clone)}>Run edited clone</button></>}><div className="history-detail"><span className="badge">Trace {selected.correlation_id}</span><span className={`badge ${selected.status === "success" ? "green" : "red"}`}>{selected.status}</span></div><label>Clone and edit query</label><textarea value={clone} onChange={(e) => setClone(e.target.value)} /><label>Redacted prompt</label><pre className="code-preview">{selected.prompt_redacted || "—"}</pre><label>Result</label><pre className="code-preview">{selected.result_summary || "—"}</pre>{selected.error_summary && <div className="action-error"><b>{selected.error_code}</b>{selected.error_summary}</div>}</Modal>}
  </>;
}

function BulkPanel({ connection }: { connection: Connection }) {
  const [form, setForm] = useState<any>({ product: connection.products[0] || "jira", target_type: "issue_keys", target_value: "", comment_mode: "personalized", instruction: "Provide a factual status follow-up and next action.", fixed_comment: "", language: "fa", tone: "formal", mode: "require_approval", skip_statuses: ["Closed"], approved: false });
  const [preview, setPreview] = useState<any>(null); const [jobs, setJobs] = useState<any[]>([]); const [busy, setBusy] = useState(false); const toast = useToast();
  const set = (key: string, value: any) => setForm((previous: any) => ({ ...previous, [key]: value, approved: key === "approved" ? value : false }));
  function payload(approved: boolean) { const isList = ["issue_keys", "page_ids"].includes(form.target_type); const key = isList ? form.target_type : form.target_type === "project" ? "project_key" : form.target_type === "saved_filter" ? "filter_id" : form.target_type === "space" ? "space_key" : form.target_type; return { product: form.product, target_type: form.target_type, target_spec: { [key]: isList ? form.target_value.split(/[\s,]+/).filter(Boolean) : form.target_value }, comment_mode: form.comment_mode, instruction: form.instruction, fixed_comment: form.fixed_comment, language: form.language, tone: form.tone, mode: form.mode, skip_statuses: form.skip_statuses, approved, idempotency_key: crypto.randomUUID(), correlation_id: crypto.randomUUID() }; }
  async function loadJobs() { try { const value = await api.get("/api/atlassian/bulk?page_size=50"); setJobs(value.items); } catch (error: any) { toast(error.message, "error"); } }
  useEffect(() => { loadJobs(); const timer = setInterval(loadJobs, 3000); return () => clearInterval(timer); }, []);
  async function dryRun() { setBusy(true); try { setPreview(await api.post(`/api/atlassian/connections/${connection.id}/bulk/preview`, payload(false))); } catch (error: any) { toast(error.message, "error"); } finally { setBusy(false); } }
  async function execute() { if (!form.approved || !preview) return toast("Dry run and final approval are required", "error"); setBusy(true); try { const body = payload(true); await api.post(`/api/atlassian/connections/${connection.id}/bulk`, body); toast("Bulk job queued", "ok"); setPreview(null); set("approved", false); loadJobs(); } catch (error: any) { toast(error.message, "error"); } finally { setBusy(false); } }
  async function action(id: number, name: "cancel" | "pause" | "resume") { try { await api.post(`/api/atlassian/bulk/${id}/${name}`); loadJobs(); } catch (error: any) { toast(error.message, "error"); } }
  const targetOptions = form.product === "jira" ? ["issue_keys", "jql", "project", "saved_filter"] : ["page_ids", "cql", "space"];
  return <><div className="card mb"><div className="card-head"><h3>Controlled bulk comment wizard</h3><span className="badge yellow">Dry run required</span></div><div className="notice danger">Bulk posts are bounded by the admin limit, skip blocked statuses, use per-target idempotency, and never run without final confirmation.</div><div className="field-row"><div><label>Product</label><select value={form.product} onChange={(e) => { set("product", e.target.value); setForm((p: any) => ({ ...p, target_type: e.target.value === "jira" ? "issue_keys" : "page_ids" })); }}><option value="jira" disabled={!connection.products.includes("jira")}>Jira</option><option value="confluence" disabled={!connection.products.includes("confluence")}>Confluence</option></select></div><div><label>Target source</label><select value={form.target_type} onChange={(e) => set("target_type", e.target.value)}>{targetOptions.map((item) => <option key={item}>{item}</option>)}</select></div></div><label>Issue keys / query / project / space</label><textarea value={form.target_value} onChange={(e) => set("target_value", e.target.value)} style={{ minHeight: 70 }} /><div className="field-row"><div><label>Comment mode</label><select value={form.comment_mode} onChange={(e) => set("comment_mode", e.target.value)}><option value="personalized">Unique per target</option><option value="shared_context">Shared instruction, personalized result</option><option value="fixed">Explicit fixed comment</option></select></div><div><label>Language</label><select value={form.language} onChange={(e) => set("language", e.target.value)}><option value="fa">Persian</option><option value="en">English</option></select></div><div><label>Tone</label><select value={form.tone} onChange={(e) => set("tone", e.target.value)}>{["formal", "technical", "concise", "executive", "follow_up", "incident_response"].map((item) => <option key={item}>{item}</option>)}</select></div></div><label>{form.comment_mode === "fixed" ? "Fixed comment" : "Generation instruction"}</label><textarea value={form.comment_mode === "fixed" ? form.fixed_comment : form.instruction} onChange={(e) => set(form.comment_mode === "fixed" ? "fixed_comment" : "instruction", e.target.value)} style={{ minHeight: 90, fontFamily: "inherit" }} /><div className="row mt"><button className="btn-primary btn-sm" onClick={dryRun} disabled={busy}>{busy ? <span className="spin" /> : "1. Dry run & sample"}</button></div>
      {preview && <div className="bulk-preview"><div className="row"><span className="stat-inline"><b>{preview.target_count}</b> exact target(s)</span><span className="faint">Admin limit: {preview.limit}</span></div>{preview.sample.map((item: any) => <div className="bulk-sample" key={item.target}><b>{item.target} · {item.title}</b><p>{item.comment}</p></div>)}<label className="approval"><input type="checkbox" checked={form.approved} onChange={(e) => set("approved", e.target.checked)} /> I reviewed the exact target count and samples and approve this bulk operation.</label><button className="btn-primary" onClick={execute} disabled={!form.approved || busy}>2. Confirm & queue job</button></div>}
    </div>
    <div className="card"><div className="card-head"><h3>Bulk job progress</h3><button className="btn-sm" onClick={loadJobs}>Refresh</button></div>{jobs.length === 0 ? <div className="empty">No bulk jobs.</div> : <div className="bulk-jobs">{jobs.map((job) => <div className="bulk-job" key={job.id}><div><div className="row"><b>#{job.id} · {job.product}</b><span className={`badge ${job.status === "completed" ? "green" : job.status === "partial" || job.status === "failed" ? "red" : "yellow"}`}>{job.status}</span></div><small>{job.success_count} success · {job.failed_count} failed · {job.skipped_count} skipped</small></div><div className="job-progress"><div className="progress-bar"><span style={{ width: `${job.progress}%` }} /></div><small>{job.progress}%</small></div><div className="row">{["pending", "running", "paused"].includes(job.status) && <button className="btn-sm btn-danger" onClick={() => action(job.id, "cancel")}>Cancel</button>}{job.status === "running" && <button className="btn-sm" onClick={() => action(job.id, "pause")}>Pause</button>}{["paused", "partial", "failed", "cancelled"].includes(job.status) && <button className="btn-sm" onClick={() => action(job.id, "resume")}>Resume failed</button>}</div></div>)}</div>}</div>
  </>;
}

function human(value: string) { return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase()); }
function fmt(value?: string) { return value ? new Date(value).toLocaleString() : "never"; }
