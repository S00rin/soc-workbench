import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Loading, Markdown, Modal, timeAgo, useToast } from "../lib";

type Item = {
  id: number;
  title: string;
  item_type: string;
  content: string;
  summary: string;
  category: string;
  tags: string[];
  source: string;
  url: string;
  favorite: boolean;
  notes: string;
  created_at: string;
  updated_at: string;
};

const BLANK = {
  title: "", item_type: "note", content: "", summary: "", category: "",
  tags: [] as string[], source: "", url: "", favorite: false, notes: "",
};

const TYPES = ["", "note", "playbook", "procedure", "query", "reference", "snippet", "lesson"];

export default function Knowledge() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [favOnly, setFavOnly] = useState(false);
  const [editing, setEditing] = useState<any | null>(null);
  const [viewing, setViewing] = useState<Item | null>(null);
  const [params, setParams] = useSearchParams();
  const toast = useToast();

  async function load() {
    try {
      const p = new URLSearchParams();
      if (q) p.set("q", q);
      if (type) p.set("item_type", type);
      if (favOnly) p.set("favorite", "true");
      setItems(await api.get(`/api/knowledge?${p}`));
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type, favOnly]);

  useEffect(() => {
    if (params.get("new") === "1") {
      setEditing({ ...BLANK });
      params.delete("new");
      setParams(params, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function remove(it: Item) {
    if (!confirm(`Delete "${it.title}"?`)) return;
    try {
      await api.del(`/api/knowledge/${it.id}`);
      toast("Deleted", "ok");
      setItems((prev) => prev?.filter((x) => x.id !== it.id) ?? null);
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  async function toggleFav(it: Item) {
    try {
      await api.put(`/api/knowledge/${it.id}`, { ...it, favorite: !it.favorite });
      setItems((prev) => prev?.map((x) => (x.id === it.id ? { ...x, favorite: !x.favorite } : x)) ?? null);
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  if (!items) return <Loading />;

  return (
    <>
      <div className="row mb">
        <input
          placeholder="Search knowledge…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load()}
          style={{ maxWidth: 280 }}
        />
        <select value={type} onChange={(e) => setType(e.target.value)} style={{ maxWidth: 150 }}>
          {TYPES.map((t) => <option key={t} value={t}>{t || "All types"}</option>)}
        </select>
        <label className="row" style={{ margin: 0, gap: 6, cursor: "pointer" }}>
          <input type="checkbox" checked={favOnly} onChange={(e) => setFavOnly(e.target.checked)} style={{ width: "auto" }} />
          <span className="dim">★ Favorites</span>
        </label>
        <button className="btn-sm" onClick={load}>Search</button>
        <span className="spacer" />
        <button className="btn-primary btn-sm" onClick={() => setEditing({ ...BLANK })}>+ New item</button>
      </div>

      {items.length === 0 ? (
        <div className="card"><div className="empty">No knowledge items. Create one, or promote a processed document.</div></div>
      ) : (
        <div className="grid cols-2">
          {items.map((it) => (
            <div className="card" key={it.id}>
              <div className="card-head">
                <h3 style={{ marginBottom: 2, cursor: "pointer" }} onClick={() => setViewing(it)}>
                  {it.favorite && <span style={{ color: "var(--yellow)" }}>★ </span>}{it.title}
                </h3>
                <span className="badge">{it.item_type}</span>
              </div>
              {it.summary && <p className="dim" style={{ marginTop: 0, fontSize: 13 }}>{it.summary.slice(0, 160)}</p>}
              {it.tags?.length > 0 && (
                <div style={{ margin: "6px 0" }}>{it.tags.slice(0, 6).map((t) => <span key={t} className="chip">{t}</span>)}</div>
              )}
              <div className="row" style={{ justifyContent: "space-between", marginTop: 8 }}>
                <span className="faint" style={{ fontSize: 12 }}>{it.category || "uncategorized"} · {timeAgo(it.updated_at)}</span>
                <span className="row" style={{ gap: 6 }}>
                  <button className="btn-sm btn-ghost" title="Favorite" onClick={() => toggleFav(it)}>{it.favorite ? "★" : "☆"}</button>
                  <button className="btn-sm" onClick={() => setViewing(it)}>View</button>
                  <button className="btn-sm" onClick={() => setEditing({ ...it })}>Edit</button>
                  <button className="btn-sm btn-danger" onClick={() => remove(it)}>Delete</button>
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {viewing && (
        <Modal title={viewing.title} onClose={() => setViewing(null)} wide
          footer={<button className="btn-sm" onClick={() => { setEditing({ ...viewing }); setViewing(null); }}>Edit</button>}>
          <div className="row mb">
            <span className="badge">{viewing.item_type}</span>
            {viewing.category && <span className="badge blue">{viewing.category}</span>}
            {viewing.url && <a href={viewing.url} target="_blank" rel="noreferrer">source ↗</a>}
          </div>
          {viewing.tags?.length > 0 && <div className="mb">{viewing.tags.map((t) => <span key={t} className="chip">{t}</span>)}</div>}
          <Markdown text={viewing.content || "_No content._"} />
          {viewing.notes && (<><hr className="hr" /><label>Notes</label><Markdown text={viewing.notes} /></>)}
        </Modal>
      )}

      {editing && (
        <ItemModal initial={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
      )}
    </>
  );
}

function ItemModal({ initial, onClose, onSaved }: { initial: any; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<any>({ ...initial, tagsText: (initial.tags || []).join(", ") });
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));
  const isEdit = !!initial.id;

  async function save() {
    if (!f.title.trim()) return toast("Title is required", "error");
    setBusy(true);
    const body = {
      title: f.title, item_type: f.item_type, content: f.content, summary: f.summary,
      category: f.category, source: f.source, url: f.url, favorite: f.favorite, notes: f.notes,
      tags: (f.tagsText || "").split(",").map((s: string) => s.trim()).filter(Boolean),
    };
    try {
      if (isEdit) await api.put(`/api/knowledge/${f.id}`, body);
      else await api.post("/api/knowledge", body);
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
      title={isEdit ? "Edit knowledge item" : "New knowledge item"}
      onClose={onClose}
      wide
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
        <div><label>Title</label><input value={f.title} onChange={(e) => set("title", e.target.value)} autoFocus /></div>
        <div style={{ maxWidth: 170 }}>
          <label>Type</label>
          <select value={f.item_type} onChange={(e) => set("item_type", e.target.value)}>
            {["note", "playbook", "procedure", "query", "reference", "snippet", "lesson"].map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
      </div>
      <label>Summary</label>
      <input value={f.summary} onChange={(e) => set("summary", e.target.value)} />
      <label>Content (Markdown)</label>
      <textarea value={f.content} onChange={(e) => set("content", e.target.value)} style={{ minHeight: 220 }} />
      <div className="field-row">
        <div><label>Category</label><input value={f.category} onChange={(e) => set("category", e.target.value)} /></div>
        <div><label>Tags (comma separated)</label><input value={f.tagsText} onChange={(e) => set("tagsText", e.target.value)} /></div>
      </div>
      <div className="field-row">
        <div><label>Source</label><input value={f.source} onChange={(e) => set("source", e.target.value)} /></div>
        <div><label>URL</label><input value={f.url} onChange={(e) => set("url", e.target.value)} /></div>
      </div>
    </Modal>
  );
}
