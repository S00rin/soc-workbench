import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Loading, Modal, useToast } from "../lib";

type Setting = { key: string; value: string; is_secret: boolean; category: string; has_value: boolean };
type Pattern = { id: number; label: string; pattern: string; is_regex: boolean; enabled: boolean; token_prefix: string };

const CATEGORY_ORDER = ["llm", "processing", "general", "jira", "splunk", "smtp", "telegram"];
const CATEGORY_LABELS: Record<string, string> = {
  llm: "LLM", processing: "Processing", general: "General", jira: "Jira",
  splunk: "Splunk", smtp: "Email (SMTP)", telegram: "Telegram",
};

function label(key: string) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// Keys that should render as a dropdown instead of a free-text field.
const SELECT_OPTIONS: Record<string, string[]> = {
  llm_provider: ["anthropic", "openai", "claude_cli"],
};

const KEY_HINTS: Record<string, string> = {
  llm_provider: "claude_cli routes analysis through your local Claude Code agent — no API key needed.",
  claude_cli_path: "Leave blank to find `claude` on PATH. Only set if it isn't found.",
  llm_model: "For claude_cli use an alias (opus / sonnet / haiku) or a full model id.",
};

export default function Settings() {
  const [settings, setSettings] = useState<Setting[] | null>(null);
  const [edited, setEdited] = useState<Record<string, string>>({});
  const [tab, setTab] = useState("llm");
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  async function load() {
    try {
      setSettings(await api.get("/api/settings"));
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const byCategory = useMemo(() => {
    const m: Record<string, Setting[]> = {};
    (settings || []).forEach((s) => (m[s.category] ??= []).push(s));
    return m;
  }, [settings]);

  const tabs = useMemo(() => {
    const present = Object.keys(byCategory);
    const ordered = CATEGORY_ORDER.filter((c) => present.includes(c));
    const extra = present.filter((c) => !CATEGORY_ORDER.includes(c));
    return [...ordered, ...extra, "patterns"];
  }, [byCategory]);

  async function save() {
    if (Object.keys(edited).length === 0) return toast("Nothing changed", "info");
    setBusy(true);
    try {
      const fresh: Setting[] = await api.put("/api/settings", { values: edited });
      setSettings(fresh);
      setEdited({});
      toast("Settings saved", "ok");
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  if (!settings) return <Loading />;

  return (
    <>
      <div className="tabs">
        {tabs.map((t) => (
          <div key={t} className={`tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
            {t === "patterns" ? "Sensitive Patterns" : CATEGORY_LABELS[t] || label(t)}
          </div>
        ))}
      </div>

      {tab === "patterns" ? (
        <Patterns />
      ) : (
        <>
          <div className="card" style={{ maxWidth: 720 }}>
            {(byCategory[tab] || []).map((s) => {
              const value = s.key in edited ? edited[s.key] : (s.is_secret ? "" : s.value);
              const options = SELECT_OPTIONS[s.key];
              return (
                <div key={s.key} style={{ marginBottom: 14 }}>
                  <label style={{ marginTop: 0 }}>
                    {label(s.key)}
                    {s.is_secret && <span className="badge" style={{ marginLeft: 8, fontSize: 10 }}>secret</span>}
                  </label>
                  {options ? (
                    <select value={value} onChange={(e) => setEdited((p) => ({ ...p, [s.key]: e.target.value }))}>
                      {options.map((o) => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : (
                    <input
                      type={s.is_secret ? "password" : "text"}
                      value={value}
                      placeholder={s.is_secret ? (s.has_value ? "•••••• (set — leave blank to keep)" : "not set") : ""}
                      onChange={(e) => setEdited((p) => ({ ...p, [s.key]: e.target.value }))}
                    />
                  )}
                  {KEY_HINTS[s.key] && <div className="faint" style={{ fontSize: 11.5, marginTop: 4 }}>{KEY_HINTS[s.key]}</div>}
                </div>
              );
            })}
          </div>
          <div className="row mt">
            <button className="btn-primary btn-sm" onClick={save} disabled={busy}>
              {busy ? <span className="spin" /> : "Save changes"}
            </button>
            {Object.keys(edited).length > 0 && <span className="dim">{Object.keys(edited).length} unsaved change(s)</span>}
          </div>
        </>
      )}
    </>
  );
}

function Patterns() {
  const [patterns, setPatterns] = useState<Pattern[] | null>(null);
  const [editing, setEditing] = useState<any | null>(null);
  const toast = useToast();

  async function load() {
    try {
      setPatterns(await api.get("/api/settings/patterns"));
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function remove(p: Pattern) {
    if (!confirm(`Delete pattern "${p.label}"?`)) return;
    try {
      await api.del(`/api/settings/patterns/${p.id}`);
      toast("Deleted", "ok");
      setPatterns((prev) => prev?.filter((x) => x.id !== p.id) ?? null);
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  if (!patterns) return <Loading />;

  return (
    <>
      <p className="dim" style={{ marginTop: 0 }}>
        Custom patterns are masked/tokenized in content before it is ever sent to the LLM. Built-in detectors (IPs, emails, keys) run in addition to these.
      </p>
      <div className="row mb">
        <span className="spacer" />
        <button className="btn-primary btn-sm" onClick={() => setEditing({ label: "", pattern: "", is_regex: true, enabled: true, token_prefix: "CUSTOM" })}>
          + Add pattern
        </button>
      </div>
      <div className="card">
        {patterns.length === 0 ? (
          <div className="empty">No custom patterns.</div>
        ) : (
          <table className="data">
            <thead>
              <tr><th>Label</th><th>Pattern</th><th>Regex</th><th>Token</th><th>Enabled</th><th></th></tr>
            </thead>
            <tbody>
              {patterns.map((p) => (
                <tr key={p.id}>
                  <td>{p.label}</td>
                  <td className="mono" style={{ wordBreak: "break-all" }}>{p.pattern}</td>
                  <td>{p.is_regex ? "yes" : "no"}</td>
                  <td><span className="badge">{p.token_prefix}</span></td>
                  <td><span className={`badge ${p.enabled ? "green" : ""}`}>{p.enabled ? "on" : "off"}</span></td>
                  <td className="row" style={{ gap: 6 }}>
                    <button className="btn-sm" onClick={() => setEditing({ ...p })}>Edit</button>
                    <button className="btn-sm btn-danger" onClick={() => remove(p)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {editing && <PatternModal initial={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
    </>
  );
}

function PatternModal({ initial, onClose, onSaved }: { initial: any; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<any>(initial);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));
  const isEdit = !!initial.id;

  async function save() {
    if (!f.label.trim() || !f.pattern.trim()) return toast("Label and pattern are required", "error");
    setBusy(true);
    const body = { label: f.label, pattern: f.pattern, is_regex: f.is_regex, enabled: f.enabled, token_prefix: f.token_prefix || "CUSTOM" };
    try {
      if (isEdit) await api.put(`/api/settings/patterns/${f.id}`, body);
      else await api.post("/api/settings/patterns", body);
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
      title={isEdit ? "Edit pattern" : "Add sensitive pattern"}
      onClose={onClose}
      footer={
        <>
          <button className="btn-sm" onClick={onClose}>Cancel</button>
          <button className="btn-primary btn-sm" onClick={save} disabled={busy}>{busy ? <span className="spin" /> : "Save"}</button>
        </>
      }
    >
      <label>Label</label>
      <input value={f.label} onChange={(e) => set("label", e.target.value)} autoFocus placeholder="e.g. Internal hostname" />
      <label>Pattern</label>
      <input value={f.pattern} onChange={(e) => set("pattern", e.target.value)} className="mono" placeholder="regex or literal string" />
      <label>Token prefix</label>
      <input value={f.token_prefix} onChange={(e) => set("token_prefix", e.target.value)} placeholder="CUSTOM" />
      <div className="row" style={{ marginTop: 14, gap: 20 }}>
        <label className="row" style={{ margin: 0, gap: 6, cursor: "pointer" }}>
          <input type="checkbox" checked={f.is_regex} onChange={(e) => set("is_regex", e.target.checked)} style={{ width: "auto" }} />
          <span className="dim">Treat as regex</span>
        </label>
        <label className="row" style={{ margin: 0, gap: 6, cursor: "pointer" }}>
          <input type="checkbox" checked={f.enabled} onChange={(e) => set("enabled", e.target.checked)} style={{ width: "auto" }} />
          <span className="dim">Enabled</span>
        </label>
      </div>
    </Modal>
  );
}
