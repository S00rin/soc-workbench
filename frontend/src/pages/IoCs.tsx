import { useEffect, useState } from "react";
import { api } from "../api";
import { Loading, Modal, timeAgo, useToast } from "../lib";

type IoC = {
  id: number;
  value: string;
  ioc_type: string;
  source: string;
  confidence: string;
  severity: string;
  tags: string[];
  related_malware: string;
  related_actor: string;
  related_incident: string;
  related_customer: string;
  notes: string;
  false_positive: boolean;
  status: string;
  score: number;
  last_sighted_at: string;
  sighting_count: number;
  watchlist: boolean;
  created_at: string;
};

const TYPES = ["", "ipv4", "domain", "url", "email", "hash", "custom"];
const STATUSES = ["", "active", "watchlist", "decaying", "expired", "retired"];
const SEV: Record<string, string> = { critical: "red", high: "red", medium: "yellow", low: "green" };
const STATUS_TONE: Record<string, string> = { active: "green", watchlist: "blue", decaying: "yellow", expired: "red", retired: "" };

export default function IoCs() {
  const [iocs, setIocs] = useState<IoC[] | null>(null);
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [watchlistOnly, setWatchlistOnly] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [extractOpen, setExtractOpen] = useState(false);
  const [busy, setBusy] = useState("");
  const toast = useToast();

  async function load() {
    try {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (type) params.set("ioc_type", type);
      if (status) params.set("status", status);
      if (watchlistOnly) params.set("watchlist", "true");
      setIocs(await api.get(`/api/iocs?${params}`));
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type, status, watchlistOnly]);

  async function remove(ioc: IoC) {
    if (!confirm(`Delete IoC "${ioc.value}"?`)) return;
    try {
      await api.del(`/api/iocs/${ioc.id}`);
      toast("Deleted", "ok");
      setIocs((prev) => prev?.filter((i) => i.id !== ioc.id) ?? null);
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  async function toggleWatch(ioc: IoC) {
    try {
      const updated: IoC = await api.patch(`/api/iocs/${ioc.id}`, { watchlist: !ioc.watchlist });
      setIocs((prev) => prev?.map((row) => row.id === ioc.id ? updated : row) ?? null);
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

  async function runLifecycle(hunt: boolean) {
    setBusy(hunt ? "hunt" : "decay");
    try {
      const result = await api.post(`/api/iocs/lifecycle/run?hunt=${hunt}`);
      toast(hunt ? `Retro-hunt sighted ${result.hunt?.sighted ?? 0}` : `Rescored ${Object.values(result.scores || {}).reduce((a: number, b: any) => a + Number(b || 0), 0)} IoCs`, "ok");
      load();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy("");
    }
  }

  if (!iocs) return <Loading />;

  return (
    <>
      <div className="row mb">
        <input
          placeholder="Search value…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load()}
          style={{ maxWidth: 280 }}
        />
        <select value={type} onChange={(e) => setType(e.target.value)} style={{ maxWidth: 150 }}>
          {TYPES.map((t) => <option key={t} value={t}>{t || "All types"}</option>)}
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ maxWidth: 150 }}>
          {STATUSES.map((t) => <option key={t} value={t}>{t || "All statuses"}</option>)}
        </select>
        <label className="row" style={{ margin: 0, gap: 6, cursor: "pointer" }}>
          <input type="checkbox" checked={watchlistOnly} onChange={(e) => setWatchlistOnly(e.target.checked)} style={{ width: "auto" }} />
          Watchlist
        </label>
        <button className="btn-sm" onClick={load}>Search</button>
        <span className="spacer" />
        <button className="btn-sm" onClick={() => api.download("/api/iocs/export/watchlist?fmt=csv", "watchlist.csv")}>Export CSV</button>
        <button className="btn-sm" onClick={() => api.download("/api/iocs/export/watchlist?fmt=stix", "watchlist.stix.json")}>Export STIX</button>
        <button className="btn-sm" onClick={() => runLifecycle(false)} disabled={busy !== ""}>{busy === "decay" ? "Scoring…" : "Rescore / decay"}</button>
        <button className="btn-sm" onClick={() => runLifecycle(true)} disabled={busy !== ""}>{busy === "hunt" ? "Hunting…" : "Splunk retro-hunt"}</button>
        <button className="btn-sm" onClick={() => setExtractOpen(true)}>⌖ Extract from text</button>
        <button className="btn-primary btn-sm" onClick={() => setAddOpen(true)}>+ Add IoC</button>
      </div>

      <div className="card">
        {iocs.length === 0 ? (
          <div className="empty">No IoCs stored. Add one or extract from text.</div>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Value</th>
                <th>Type</th>
                <th>Severity</th>
                <th>Score</th>
                <th>Status</th>
                <th>Sightings</th>
                <th>Source</th>
                <th>Added</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {iocs.map((i) => (
                <tr key={i.id}>
                  <td className="mono" style={{ wordBreak: "break-all" }}>
                    {i.value}
                    {i.false_positive && <span className="badge yellow" style={{ marginLeft: 6 }}>FP</span>}
                    {i.watchlist && <span className="badge blue" style={{ marginLeft: 6 }}>WL</span>}
                  </td>
                  <td><span className="badge blue">{i.ioc_type}</span></td>
                  <td><span className={`badge ${SEV[i.severity] || ""}`}>{i.severity}</span></td>
                  <td className="mono">{Math.round(i.score ?? 100)}</td>
                  <td><span className={`badge ${STATUS_TONE[i.status] || ""}`}>{i.status || "active"}</span></td>
                  <td className="dim">{i.sighting_count || 0}</td>
                  <td className="dim">{i.source || "—"}</td>
                  <td className="dim">{timeAgo(i.created_at)}</td>
                  <td className="row" style={{ justifyContent: "flex-end" }}>
                    <button className="btn-sm" onClick={() => toggleWatch(i)}>{i.watchlist ? "Unwatch" : "Watch"}</button>
                    <button className="btn-sm btn-danger" onClick={() => remove(i)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {addOpen && <AddModal onClose={() => setAddOpen(false)} onSaved={() => { setAddOpen(false); load(); }} />}
      {extractOpen && <ExtractModal onClose={() => setExtractOpen(false)} onDone={() => { setExtractOpen(false); load(); }} />}
    </>
  );
}

function AddModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ value: "", ioc_type: "ipv4", source: "", severity: "medium", confidence: "medium", notes: "" });
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const set = (k: string, v: any) => setF((p) => ({ ...p, [k]: v }));

  async function save() {
    if (!f.value.trim()) return toast("Value is required", "error");
    setBusy(true);
    try {
      await api.post("/api/iocs", f);
      toast("IoC added", "ok");
      onSaved();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Add IoC"
      onClose={onClose}
      footer={
        <>
          <button className="btn-sm" onClick={onClose}>Cancel</button>
          <button className="btn-primary btn-sm" onClick={save} disabled={busy}>{busy ? <span className="spin" /> : "Add"}</button>
        </>
      }
    >
      <label>Value</label>
      <input value={f.value} onChange={(e) => set("value", e.target.value)} autoFocus className="mono" />
      <div className="field-row">
        <div>
          <label>Type</label>
          <select value={f.ioc_type} onChange={(e) => set("ioc_type", e.target.value)}>
            {["ipv4", "domain", "url", "email", "hash", "custom"].map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label>Severity</label>
          <select value={f.severity} onChange={(e) => set("severity", e.target.value)}>
            {["low", "medium", "high", "critical"].map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label>Confidence</label>
          <select value={f.confidence} onChange={(e) => set("confidence", e.target.value)}>
            {["low", "medium", "high"].map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
      </div>
      <label>Source</label>
      <input value={f.source} onChange={(e) => set("source", e.target.value)} />
      <label>Notes</label>
      <textarea value={f.notes} onChange={(e) => set("notes", e.target.value)} style={{ minHeight: 70 }} />
    </Modal>
  );
}

function ExtractModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [text, setText] = useState("");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  async function run() {
    if (!text.trim()) return toast("Paste some text first", "error");
    setBusy(true);
    try {
      const created: any[] = await api.post("/api/iocs/extract", { text, source });
      toast(`${created.length} new IoC(s) stored`, "ok");
      onDone();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Extract IoCs from text"
      onClose={onClose}
      footer={
        <>
          <button className="btn-sm" onClick={onClose}>Cancel</button>
          <button className="btn-primary btn-sm" onClick={run} disabled={busy}>{busy ? <span className="spin" /> : "Extract & store"}</button>
        </>
      }
    >
      <p className="dim" style={{ marginTop: 0 }}>Paste logs, alerts, or a report. IPs, domains, URLs, emails and hashes are extracted and de-duplicated.</p>
      <label>Text</label>
      <textarea value={text} onChange={(e) => setText(e.target.value)} style={{ minHeight: 200 }} autoFocus />
      <label>Source label (optional)</label>
      <input value={source} onChange={(e) => setSource(e.target.value)} placeholder="e.g. Alert #1234" />
    </Modal>
  );
}
