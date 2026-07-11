import { useEffect, useState } from "react";
import { api } from "../api";
import { Markdown, Modal, useToast } from "../lib";

export default function Splunk() {
  const [spl, setSpl] = useState('search index=* | head 100');
  const [earliest, setEarliest] = useState("-24h");
  const [latest, setLatest] = useState("now");
  const [data, setData] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [instruction, setInstruction] = useState("Analyze these results: notable patterns, anomalies, and recommendations.");
  const [analysis, setAnalysis] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [savedOpen, setSavedOpen] = useState(false);
  const toast = useToast();

  async function testConn() {
    try {
      const res = await api.post("/api/splunk/test");
      toast(`Connected: ${res.version || res.messages || JSON.stringify(res).slice(0, 60)}`, "ok");
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  async function search() {
    setBusy(true);
    setAnalysis("");
    try {
      setData(await api.post("/api/splunk/search", { spl, earliest, latest }));
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function analyze() {
    setAnalyzing(true);
    try {
      const res = await api.post("/api/splunk/analyze", { spl, earliest, latest, instruction });
      setAnalysis(res.result);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setAnalyzing(false);
    }
  }

  const fields: string[] = data?.fields || (data?.results?.[0] ? Object.keys(data.results[0]) : []);
  const rows: any[] = data?.results || [];

  return (
    <>
      <div className="card mb">
        <div className="card-head">
          <h3>SPL search</h3>
          <div className="row" style={{ gap: 6 }}>
            <button className="btn-sm" onClick={testConn}>Test connection</button>
            <button className="btn-sm" onClick={() => setSavedOpen(true)}>Saved searches</button>
          </div>
        </div>
        <textarea value={spl} onChange={(e) => setSpl(e.target.value)} style={{ minHeight: 70 }} />
        <div className="field-row" style={{ marginTop: 10 }}>
          <div><label>Earliest</label><input className="mono" value={earliest} onChange={(e) => setEarliest(e.target.value)} /></div>
          <div><label>Latest</label><input className="mono" value={latest} onChange={(e) => setLatest(e.target.value)} /></div>
        </div>
        <div className="row mt">
          <button className="btn-primary btn-sm" onClick={search} disabled={busy}>{busy ? <span className="spin" /> : "Run search"}</button>
          <span className="faint" style={{ fontSize: 12 }}>Read-only. Allowed indexes & limits enforced from Settings → Splunk.</span>
        </div>
      </div>

      {data && (
        <div className="card mb">
          <div className="card-head"><h3>{data.count ?? rows.length} result(s)</h3></div>
          {rows.length === 0 ? <div className="empty">No results.</div> : (
            <div style={{ overflowX: "auto" }}>
              <table className="data">
                <thead><tr>{fields.map((f) => <th key={f}>{f}</th>)}</tr></thead>
                <tbody>
                  {rows.slice(0, 200).map((r, i) => (
                    <tr key={i}>{fields.map((f) => <td key={f} className="mono" style={{ maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis" }}>{String(r[f] ?? "")}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <div className="card">
        <div className="card-head"><h3>AI analysis</h3></div>
        <label>Instruction</label>
        <textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} style={{ minHeight: 60, fontFamily: "inherit" }} />
        <div className="row mt">
          <button className="btn-primary btn-sm" onClick={analyze} disabled={analyzing}>{analyzing ? <span className="spin" /> : "Analyze results"}</button>
        </div>
        {analysis && (<><hr className="hr" /><Markdown text={analysis} /></>)}
      </div>

      {savedOpen && <SavedModal onClose={() => setSavedOpen(false)} onPick={(q) => { setSpl(q); setSavedOpen(false); }} />}
    </>
  );
}

function SavedModal({ onClose, onPick }: { onClose: () => void; onPick: (q: string) => void }) {
  const [saved, setSaved] = useState<any[] | null>(null);
  const [err, setErr] = useState("");
  const toast = useToast();
  useEffect(() => {
    api.get("/api/splunk/saved").then((d) => setSaved(Array.isArray(d) ? d : d.entry || d.searches || [])).catch((e) => setErr(e.message));
  }, []);
  return (
    <Modal title="Saved searches" onClose={onClose}>
      {err && <div className="badge red" style={{ display: "block", padding: 10 }}>{err}</div>}
      {!saved && !err && <div className="dim">Loading…</div>}
      {saved && saved.length === 0 && <div className="empty">None found.</div>}
      {saved && (
        <div className="list">
          {saved.map((s: any, i: number) => {
            const name = s.name || s.title || `search ${i + 1}`;
            const q = s.search || s.query || s.spl || "";
            return (
              <div className="list-row" key={i}>
                <span>{name}</span>
                <button className="btn-sm" disabled={!q} onClick={() => q ? onPick(q) : toast("No query on this entry", "info")}>Use</button>
              </div>
            );
          })}
        </div>
      )}
    </Modal>
  );
}
