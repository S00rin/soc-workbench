import { useEffect, useState } from "react";
import { api } from "../api";
import { Loading, Markdown, Modal, useToast } from "../lib";

type Item = {
  id: number;
  title: string;
  source: string;
  url: string;
  category: string;
  relevance: number;
  tags: string[];
  read: boolean;
  saved: boolean;
  published_at: string;
  summary_en: string;
  summary_fa: string;
};

export default function Intel() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [savedOnly, setSavedOnly] = useState(false);
  const [kind, setKind] = useState<"feed" | "url">("feed");
  const [source, setSource] = useState("");
  const [summarize, setSummarize] = useState(false);
  const [busy, setBusy] = useState(false);
  const [viewing, setViewing] = useState<number | null>(null);
  const toast = useToast();

  async function load() {
    try {
      setItems(await api.get(`/api/intel?saved=${savedOnly}`));
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedOnly]);

  async function collect() {
    if (!source.trim()) return toast(kind === "feed" ? "Enter an RSS/Atom feed URL" : "Enter an article URL", "error");
    setBusy(true);
    try {
      const res = await api.post("/api/intel/collect", { kind, source, limit: 20, summarize });
      toast(`Collected ${res.collected}, ${res.new} new`, "ok");
      setSource("");
      load();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function toggleSave(it: Item) {
    try {
      await api.patch(`/api/intel/${it.id}`, { saved: !it.saved });
      setItems((prev) => prev?.map((x) => (x.id === it.id ? { ...x, saved: !x.saved } : x)).filter((x) => (savedOnly ? x.saved : true)) ?? null);
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  if (!items) return <Loading />;

  return (
    <>
      <div className="card mb">
        <div className="card-head"><h3>Collect intelligence</h3></div>
        <div className="row">
          <div className="pill-toggle">
            <button className={kind === "feed" ? "active" : ""} onClick={() => setKind("feed")}>RSS feed</button>
            <button className={kind === "url" ? "active" : ""} onClick={() => setKind("url")}>Single URL</button>
          </div>
          <input
            className="mono"
            style={{ flex: 1, minWidth: 240 }}
            placeholder={kind === "feed" ? "https://…/feed.xml" : "https://…/article"}
            value={source}
            onChange={(e) => setSource(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && collect()}
          />
          <label className="row" style={{ margin: 0, gap: 6, cursor: "pointer" }}>
            <input type="checkbox" checked={summarize} onChange={(e) => setSummarize(e.target.checked)} style={{ width: "auto" }} />
            <span className="dim">LLM summaries (EN/FA)</span>
          </label>
          <button className="btn-primary btn-sm" onClick={collect} disabled={busy}>{busy ? <span className="spin" /> : "Collect"}</button>
        </div>
      </div>

      <div className="row mb">
        <label className="row" style={{ margin: 0, gap: 6, cursor: "pointer" }}>
          <input type="checkbox" checked={savedOnly} onChange={(e) => setSavedOnly(e.target.checked)} style={{ width: "auto" }} />
          <span className="dim">★ Saved only</span>
        </label>
        <span className="spacer" />
        <button className="btn-sm" onClick={load}>↻ Refresh</button>
      </div>

      {items.length === 0 ? (
        <div className="card"><div className="empty">No intel items. Collect from a feed or URL above.</div></div>
      ) : (
        <div className="list card">
          {items.map((it) => (
            <div className="list-row" key={it.id} style={{ alignItems: "flex-start" }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ cursor: "pointer", fontWeight: it.read ? 400 : 600 }} onClick={() => setViewing(it.id)}>
                  {it.title}
                </div>
                <div className="meta">
                  <span className="badge">{it.category}</span> {it.source}
                  {it.published_at ? ` · ${it.published_at.slice(0, 16)}` : ""}
                  {it.relevance > 0 ? ` · relevance ${it.relevance.toFixed(2)}` : ""}
                </div>
              </div>
              <span className="row" style={{ gap: 6 }}>
                <button className="btn-sm btn-ghost" title="Save" onClick={() => toggleSave(it)}>{it.saved ? "★" : "☆"}</button>
                <button className="btn-sm" onClick={() => setViewing(it.id)}>Open</button>
              </span>
            </div>
          ))}
        </div>
      )}

      {viewing !== null && <IntelModal id={viewing} onClose={() => setViewing(null)} onChanged={load} />}
    </>
  );
}

function IntelModal({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const [item, setItem] = useState<any | null>(null);
  const toast = useToast();

  async function load() {
    try {
      setItem(await api.get(`/api/intel/${id}`));
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function toKnowledge() {
    try {
      await api.post(`/api/intel/${id}/to-knowledge`);
      toast("Added to knowledge base", "ok");
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  if (!item) return <Modal title="Intel" onClose={onClose}><Loading /></Modal>;

  const body = item.summary_en || item.content || "_No summary or content extracted._";

  return (
    <Modal title={item.title} onClose={onClose} wide
      footer={
        <>
          <button className="btn-sm" style={{ marginRight: "auto" }} onClick={toKnowledge}>❏ Save to KB</button>
          {item.url && <a className="btn btn-sm" href={item.url} target="_blank" rel="noreferrer">Open source ↗</a>}
          <button className="btn-sm" onClick={onClose}>Close</button>
        </>
      }
    >
      <div className="row mb">
        <span className="badge">{item.category}</span>
        <span className="dim">{item.source}{item.published_at ? ` · ${item.published_at.slice(0, 16)}` : ""}</span>
      </div>
      <Markdown text={body} />
      {item.summary_fa && (<><hr className="hr" /><label>خلاصه فارسی</label><div dir="rtl"><Markdown text={item.summary_fa} /></div></>)}
    </Modal>
  );
}
