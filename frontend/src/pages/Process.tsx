import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Loading, Markdown, Modal, timeAgo, useToast } from "../lib";

type Processed = {
  title: string;
  original_text: string;
  markdown: string;
  protected_markdown: string;
  optimized_markdown: string;
  summary: string;
  entities: Record<string, any>;
  protection_mode: string;
  optimization_mode: string;
  token_estimate: number;
  protection_counts: Record<string, number>;
  source_type: string;
  source_ref: string;
  stored_path: string;
  mime: string;
};

type DocListItem = {
  id: number;
  title: string;
  source_type: string;
  summary: string;
  token_estimate: number;
  status: string;
  created_at: string;
};

const PROTECTION = ["mask", "tokenize", "remove"];
const OPTIMIZATION = ["minimal", "balanced", "detailed", "forensic"];
const KINDS = ["text", "markdown", "html", "csv", "json"];

export default function Process() {
  const [mode, setMode] = useState<"file" | "text" | "url">("file");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [kind, setKind] = useState("text");
  const [title, setTitle] = useState("");
  const [protection, setProtection] = useState("mask");
  const [optimization, setOptimization] = useState("balanced");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Processed | null>(null);
  const [docs, setDocs] = useState<DocListItem[] | null>(null);
  const [openDoc, setOpenDoc] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const toast = useToast();

  async function loadDocs() {
    try {
      setDocs(await api.get("/api/documents?limit=50"));
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  useEffect(() => {
    loadDocs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function run() {
    setBusy(true);
    setResult(null);
    try {
      let res: Processed;
      if (mode === "file") {
        if (!file) { setBusy(false); return toast("Choose a file first", "error"); }
        const form = new FormData();
        form.append("file", file);
        form.append("protection_mode", protection);
        form.append("optimization_mode", optimization);
        res = await api.upload("/api/documents/process-file", form);
      } else {
        const body = {
          title: title || (mode === "url" ? url : "Untitled"),
          text: mode === "text" ? text : null,
          url: mode === "url" ? url : null,
          kind,
          protection_mode: protection,
          optimization_mode: optimization,
        };
        if (mode === "text" && !text.trim()) { setBusy(false); return toast("Enter some text", "error"); }
        if (mode === "url" && !url.trim()) { setBusy(false); return toast("Enter a URL", "error"); }
        res = await api.post("/api/documents/process-text", body);
      }
      setResult(res);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function saveDoc() {
    if (!result) return;
    try {
      const doc = await api.post("/api/documents", {
        title: title || result.title,
        source_type: result.source_type,
        source_ref: result.source_ref,
        mime: result.mime,
        stored_path: result.stored_path,
        original_text: result.original_text,
        markdown: result.markdown,
        protected_markdown: result.protected_markdown,
        optimized_markdown: result.optimized_markdown,
        summary: result.summary,
        entities: result.entities,
        protection_mode: result.protection_mode,
        optimization_mode: result.optimization_mode,
        token_estimate: result.token_estimate,
      });
      toast("Saved to documents", "ok");
      setResult(null);
      setFile(null);
      setText("");
      setUrl("");
      setTitle("");
      if (fileRef.current) fileRef.current.value = "";
      await loadDocs();
      setOpenDoc(doc.id);
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  async function removeDoc(id: number) {
    if (!confirm("Delete this document?")) return;
    try {
      await api.del(`/api/documents/${id}`);
      toast("Deleted", "ok");
      setDocs((prev) => prev?.filter((d) => d.id !== id) ?? null);
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  return (
    <>
      <div className="card mb">
        <div className="row mb">
          <div className="pill-toggle">
            {(["file", "text", "url"] as const).map((m) => (
              <button key={m} className={mode === m ? "active" : ""} onClick={() => { setMode(m); setResult(null); }}>
                {m === "file" ? "Upload file" : m === "text" ? "Paste text" : "Fetch URL"}
              </button>
            ))}
          </div>
        </div>

        {mode === "file" && (
          <div>
            <label>File (PDF, DOCX, TXT, MD, CSV, JSON, HTML, images…)</label>
            <input ref={fileRef} type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </div>
        )}
        {mode === "text" && (
          <div>
            <div className="field-row">
              <div><label>Title</label><input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Untitled" /></div>
              <div style={{ maxWidth: 160 }}>
                <label>Format</label>
                <select value={kind} onChange={(e) => setKind(e.target.value)}>{KINDS.map((k) => <option key={k}>{k}</option>)}</select>
              </div>
            </div>
            <label>Content</label>
            <textarea value={text} onChange={(e) => setText(e.target.value)} style={{ minHeight: 180 }} placeholder="Paste logs, an alert, a report…" />
          </div>
        )}
        {mode === "url" && (
          <div>
            <label>URL</label>
            <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" className="mono" />
            <label>Title (optional)</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
        )}

        <div className="field-row" style={{ marginTop: 14 }}>
          <div>
            <label>Sensitive-data protection</label>
            <select value={protection} onChange={(e) => setProtection(e.target.value)}>
              {PROTECTION.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div>
            <label>Optimization</label>
            <select value={optimization} onChange={(e) => setOptimization(e.target.value)}>
              {OPTIMIZATION.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </div>
        </div>

        <div className="row mt">
          <button className="btn-primary btn-sm" onClick={run} disabled={busy}>
            {busy ? <span className="spin" /> : "Process"}
          </button>
          <span className="faint" style={{ fontSize: 12 }}>Content is protected before it can be sent to any LLM.</span>
        </div>
      </div>

      {result && <ResultPanel result={result} onSave={saveDoc} onDiscard={() => setResult(null)} />}

      <div className="card">
        <div className="card-head"><h3>Saved documents</h3><button className="btn-sm" onClick={loadDocs}>↻</button></div>
        {!docs ? <Loading /> : docs.length === 0 ? (
          <div className="empty">Nothing saved yet.</div>
        ) : (
          <table className="data">
            <thead><tr><th>Title</th><th>Source</th><th>Tokens</th><th>Created</th><th></th></tr></thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id}>
                  <td style={{ cursor: "pointer" }} onClick={() => setOpenDoc(d.id)}>{d.title}</td>
                  <td><span className="badge">{d.source_type}</span></td>
                  <td className="dim">{d.token_estimate.toLocaleString()}</td>
                  <td className="dim">{timeAgo(d.created_at)}</td>
                  <td className="row" style={{ gap: 6 }}>
                    <button className="btn-sm" onClick={() => setOpenDoc(d.id)}>Open</button>
                    <button className="btn-sm btn-danger" onClick={() => removeDoc(d.id)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {openDoc !== null && (
        <DocModal id={openDoc} onClose={() => setOpenDoc(null)} onChanged={loadDocs} />
      )}
    </>
  );
}

function ResultPanel({ result, onSave, onDiscard }: { result: Processed; onSave: () => void; onDiscard: () => void }) {
  const [tab, setTab] = useState("summary");
  const counts = Object.entries(result.protection_counts || {}).filter(([, n]) => n > 0);
  const views: Record<string, string> = {
    summary: result.summary || "_No summary._",
    optimized: result.optimized_markdown,
    protected: result.protected_markdown,
    markdown: result.markdown,
  };

  return (
    <div className="card mb">
      <div className="card-head">
        <h3>Preview — {result.title}</h3>
        <div className="row" style={{ gap: 6 }}>
          <button className="btn-sm" onClick={onDiscard}>Discard</button>
          <button className="btn-primary btn-sm" onClick={onSave}>Save to documents</button>
        </div>
      </div>
      <div className="row mb" style={{ gap: 8 }}>
        <span className="badge blue">{result.token_estimate.toLocaleString()} tokens</span>
        <span className="badge">protect: {result.protection_mode}</span>
        <span className="badge">opt: {result.optimization_mode}</span>
        {counts.length > 0 && <span className="badge yellow">{counts.reduce((a, [, n]) => a + n, 0)} redactions</span>}
      </div>
      {counts.length > 0 && (
        <div className="mb">{counts.map(([k, n]) => <span key={k} className="chip">{k}: {n}</span>)}</div>
      )}
      <div className="tabs">
        {["summary", "optimized", "protected", "markdown", "entities"].map((t) => (
          <div key={t} className={`tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>{t}</div>
        ))}
      </div>
      {tab === "entities" ? (
        <pre className="md" style={{ background: "var(--bg)", padding: 12, borderRadius: 7, overflowX: "auto", fontSize: 12.5 }}>
          {JSON.stringify(result.entities, null, 2)}
        </pre>
      ) : (
        <Markdown text={views[tab] || "_empty_"} />
      )}
    </div>
  );
}

function DocModal({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const [doc, setDoc] = useState<any | null>(null);
  const [tab, setTab] = useState("analysis");
  const [instruction, setInstruction] = useState("Analyze this content for a SOC analyst. Summarize key findings, risks, and action items.");
  const [useVersion, setUseVersion] = useState("optimized");
  const [analyzing, setAnalyzing] = useState(false);
  const toast = useToast();

  async function load() {
    try {
      setDoc(await api.get(`/api/documents/${id}`));
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function analyze() {
    setAnalyzing(true);
    try {
      await api.post(`/api/documents/${id}/analyze`, { instruction, use_version: useVersion });
      toast("Analysis queued — check the Jobs page. Reopen to see the result.", "ok");
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setAnalyzing(false);
    }
  }

  async function toKnowledge() {
    try {
      await api.post(`/api/documents/${id}/to-knowledge`);
      toast("Added to knowledge base", "ok");
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  if (!doc) return <Modal title="Document" onClose={onClose}><Loading /></Modal>;

  const views: Record<string, string> = {
    analysis: doc.ai_analysis || "_Not analyzed yet. Run an analysis below._",
    summary: doc.summary || "_No summary._",
    optimized: doc.optimized_markdown,
    protected: doc.protected_markdown,
  };

  return (
    <Modal
      title={doc.title}
      onClose={onClose}
      wide
      footer={
        <>
          <button className="btn-sm" style={{ marginRight: "auto" }} onClick={toKnowledge}>❏ Save to KB</button>
          <button className="btn-sm" onClick={onClose}>Close</button>
        </>
      }
    >
      <div className="row mb" style={{ gap: 8 }}>
        <span className="badge">{doc.source_type}</span>
        <span className="badge blue">{doc.token_estimate?.toLocaleString()} tokens</span>
        <span className="dim">{timeAgo(doc.created_at)}</span>
      </div>

      <div className="tabs">
        {["analysis", "summary", "optimized", "protected"].map((t) => (
          <div key={t} className={`tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>{t}</div>
        ))}
      </div>
      <div style={{ maxHeight: 320, overflowY: "auto" }}>
        <Markdown text={views[tab] || "_empty_"} />
      </div>

      <hr className="hr" />
      <h3 style={{ fontSize: 14 }}>Run LLM analysis</h3>
      <p className="faint" style={{ fontSize: 12, marginTop: 0 }}>Only the protected/optimized text is sent to the provider.</p>
      <label>Instruction</label>
      <textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} style={{ minHeight: 70, fontFamily: "inherit" }} />
      <div className="row mt">
        <select value={useVersion} onChange={(e) => setUseVersion(e.target.value)} style={{ maxWidth: 160 }}>
          <option value="optimized">optimized version</option>
          <option value="protected">protected version</option>
        </select>
        <button className="btn-primary btn-sm" onClick={analyze} disabled={analyzing}>
          {analyzing ? <span className="spin" /> : "Analyze"}
        </button>
        <button className="btn-sm" onClick={load}>↻ Refresh result</button>
      </div>
    </Modal>
  );
}
