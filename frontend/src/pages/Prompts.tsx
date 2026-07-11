import { useEffect, useState } from "react";
import { api } from "../api";
import { Loading, Markdown, Modal, useToast } from "../lib";

type Prompt = {
  id: number;
  name: string;
  category: string;
  description: string;
  system_prompt: string;
  user_template: string;
  variables: string[];
  model: string;
  max_tokens: number;
  language: string;
  usage_count: number;
  favorite: boolean;
};

const BLANK = {
  name: "", category: "Custom", description: "", system_prompt: "", user_template: "",
  variables: [] as string[], model: "", max_tokens: 0, language: "en", favorite: false,
};

export default function Prompts() {
  const [prompts, setPrompts] = useState<Prompt[] | null>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [category, setCategory] = useState("");
  const [editing, setEditing] = useState<any | null>(null);
  const [testing, setTesting] = useState<Prompt | null>(null);
  const toast = useToast();

  async function load() {
    try {
      const qs = category ? `?category=${encodeURIComponent(category)}` : "";
      const [p, c] = await Promise.all([api.get(`/api/prompts${qs}`), api.get("/api/prompts/categories")]);
      setPrompts(p);
      setCategories(c);
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category]);

  async function remove(p: Prompt) {
    if (!confirm(`Delete prompt "${p.name}"?`)) return;
    try {
      await api.del(`/api/prompts/${p.id}`);
      toast("Deleted", "ok");
      setPrompts((prev) => prev?.filter((x) => x.id !== p.id) ?? null);
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  if (!prompts) return <Loading />;

  return (
    <>
      <div className="row mb">
        <select value={category} onChange={(e) => setCategory(e.target.value)} style={{ maxWidth: 220 }}>
          <option value="">All categories</option>
          {categories.map((c) => <option key={c}>{c}</option>)}
        </select>
        <span className="spacer" />
        <button className="btn-primary btn-sm" onClick={() => setEditing({ ...BLANK })}>+ New prompt</button>
      </div>

      {prompts.length === 0 ? (
        <div className="card"><div className="empty">No prompts yet. Build a reusable template for Jira/Splunk/report analysis.</div></div>
      ) : (
        <div className="grid cols-2">
          {prompts.map((p) => (
            <div className="card" key={p.id}>
              <div className="card-head">
                <h3 style={{ marginBottom: 2 }}>{p.favorite && <span style={{ color: "var(--yellow)" }}>★ </span>}{p.name}</h3>
                <span className="badge blue">{p.category}</span>
              </div>
              {p.description && <p className="dim" style={{ marginTop: 0, fontSize: 13 }}>{p.description.slice(0, 140)}</p>}
              <div className="row" style={{ justifyContent: "space-between", marginTop: 8 }}>
                <span className="faint" style={{ fontSize: 12 }}>used {p.usage_count}× · {p.language}{p.model ? ` · ${p.model}` : ""}</span>
                <span className="row" style={{ gap: 6 }}>
                  <button className="btn-sm" onClick={() => setTesting(p)}>Test</button>
                  <button className="btn-sm" onClick={() => setEditing({ ...p })}>Edit</button>
                  <button className="btn-sm btn-danger" onClick={() => remove(p)}>Delete</button>
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && <PromptModal initial={editing} categories={categories} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
      {testing && <TestModal prompt={testing} onClose={() => setTesting(null)} />}
    </>
  );
}

function PromptModal({ initial, categories, onClose, onSaved }: { initial: any; categories: string[]; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<any>({ ...initial, varsText: (initial.variables || []).join(", ") });
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));
  const isEdit = !!initial.id;

  async function save() {
    if (!f.name.trim()) return toast("Name is required", "error");
    setBusy(true);
    const body = {
      name: f.name, category: f.category, description: f.description,
      system_prompt: f.system_prompt, user_template: f.user_template,
      variables: (f.varsText || "").split(",").map((s: string) => s.trim()).filter(Boolean),
      model: f.model, max_tokens: Number(f.max_tokens) || 0, language: f.language, favorite: f.favorite,
    };
    try {
      if (isEdit) await api.put(`/api/prompts/${f.id}`, body);
      else await api.post("/api/prompts", body);
      toast(isEdit ? "Updated" : "Created", "ok");
      onSaved();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={isEdit ? "Edit prompt" : "New prompt"} onClose={onClose} wide
      footer={
        <>
          <label className="row" style={{ margin: 0, gap: 6, cursor: "pointer", marginRight: "auto" }}>
            <input type="checkbox" checked={f.favorite} onChange={(e) => set("favorite", e.target.checked)} style={{ width: "auto" }} />
            <span className="dim">★ Favorite</span>
          </label>
          <button className="btn-sm" onClick={onClose}>Cancel</button>
          <button className="btn-primary btn-sm" onClick={save} disabled={busy}>{busy ? <span className="spin" /> : "Save"}</button>
        </>
      }
    >
      <div className="field-row">
        <div><label>Name</label><input value={f.name} onChange={(e) => set("name", e.target.value)} autoFocus /></div>
        <div>
          <label>Category</label>
          <select value={f.category} onChange={(e) => set("category", e.target.value)}>
            {categories.map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
      </div>
      <label>Description</label>
      <input value={f.description} onChange={(e) => set("description", e.target.value)} />
      <label>System prompt</label>
      <textarea value={f.system_prompt} onChange={(e) => set("system_prompt", e.target.value)} style={{ minHeight: 80 }} />
      <label>User template <span className="faint">— use {"{{variable}}"} placeholders</span></label>
      <textarea value={f.user_template} onChange={(e) => set("user_template", e.target.value)} style={{ minHeight: 120 }} />
      <div className="field-row">
        <div><label>Variables (comma separated)</label><input value={f.varsText} onChange={(e) => set("varsText", e.target.value)} /></div>
        <div style={{ maxWidth: 120 }}>
          <label>Language</label>
          <select value={f.language} onChange={(e) => set("language", e.target.value)}>
            <option value="en">en</option><option value="fa">fa</option>
          </select>
        </div>
      </div>
      <div className="field-row">
        <div><label>Model override (optional)</label><input value={f.model} onChange={(e) => set("model", e.target.value)} placeholder="default from Settings" /></div>
        <div style={{ maxWidth: 140 }}><label>Max tokens (0 = default)</label><input type="number" value={f.max_tokens} onChange={(e) => set("max_tokens", e.target.value)} /></div>
      </div>
    </Modal>
  );
}

function TestModal({ prompt, onClose }: { prompt: Prompt; onClose: () => void }) {
  const [userPrompt, setUserPrompt] = useState(prompt.user_template);
  const [vars, setVars] = useState<Record<string, string>>(Object.fromEntries((prompt.variables || []).map((v) => [v, ""])));
  const [result, setResult] = useState<{ result: string; model: string; tokens: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  async function run() {
    setBusy(true);
    setResult(null);
    try {
      const res = await api.post(`/api/prompts/${prompt.id}/test`, {
        system_prompt: prompt.system_prompt,
        user_prompt: userPrompt,
        variables: vars,
      });
      setResult(res);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={`Test: ${prompt.name}`} onClose={onClose} wide
      footer={<button className="btn-primary btn-sm" onClick={run} disabled={busy}>{busy ? <span className="spin" /> : "Run"}</button>}>
      {(prompt.variables || []).length > 0 && (
        <>
          <label>Variables</label>
          <div className="field-row">
            {prompt.variables.map((v) => (
              <div key={v}>
                <label style={{ marginTop: 0 }}>{v}</label>
                <input value={vars[v] || ""} onChange={(e) => setVars((p) => ({ ...p, [v]: e.target.value }))} />
              </div>
            ))}
          </div>
        </>
      )}
      <label>User prompt</label>
      <textarea value={userPrompt} onChange={(e) => setUserPrompt(e.target.value)} style={{ minHeight: 120 }} />
      {result && (
        <>
          <hr className="hr" />
          <div className="row mb"><span className="badge blue">{result.model}</span><span className="badge">{result.tokens} tokens</span></div>
          <Markdown text={result.result} />
        </>
      )}
    </Modal>
  );
}
